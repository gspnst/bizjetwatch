"""Background collection loop. Runs in its own thread inside the web process so
data is captured whenever the machine is awake -- independent of any browser."""
import time, threading
from . import db, opensky, detector, airports, config

class Poller:
    def __init__(self):
        self.lock = threading.Lock()
        self.tracks = {}                 # icao24 -> Track
        self.airport = None              # current airport dict
        self.poll_sec = config.DEFAULT_POLL_SEC
        self.radius_km = config.DEFAULT_RADIUS_KM
        self.include_turboprops = config.DEFAULT_INCLUDE_TURBOPROPS
        self.collecting = True
        self.last_sync = None
        self.last_error = None
        self._stop = threading.Event()
        self._meta_cache = {}            # icao24 -> dict (per-process)

    # ---- config loaded from / saved to DB ----
    def load_from_db(self):
        con = db.connect()
        s = db.all_settings(con); con.close()
        self.airport = airports.get(s.get("airport", config.DEFAULT_AIRPORT)) or airports.get(config.DEFAULT_AIRPORT)
        self.poll_sec = int(s.get("poll_sec", config.DEFAULT_POLL_SEC))
        self.radius_km = float(s.get("radius_km", config.DEFAULT_RADIUS_KM))
        self.include_turboprops = s.get("include_turboprops", "0") == "1"
        self.collecting = s.get("collecting", "1") == "1"

    def set_airport(self, icao):
        ap = airports.get(icao)
        if not ap:
            return False
        con = db.connect(); db.set_setting(con, "airport", ap["icao"]); con.close()
        with self.lock:
            self.airport = ap
            self.tracks.clear()          # different airspace -> reset trajectories
        return True

    def set_options(self, poll_sec=None, radius_km=None, include_turboprops=None, collecting=None):
        con = db.connect()
        with self.lock:
            if poll_sec is not None:
                self.poll_sec = max(5, int(poll_sec)); db.set_setting(con, "poll_sec", self.poll_sec)
            if radius_km is not None:
                self.radius_km = float(radius_km); db.set_setting(con, "radius_km", self.radius_km)
            if include_turboprops is not None:
                self.include_turboprops = bool(include_turboprops)
                db.set_setting(con, "include_turboprops", "1" if include_turboprops else "0")
            if collecting is not None:
                self.collecting = bool(collecting)
                db.set_setting(con, "collecting", "1" if collecting else "0")
                if not collecting:
                    self.tracks.clear()
        con.close()

    # ---- enrichment ----
    def _meta(self, con, icao24):
        if icao24 in self._meta_cache:
            return self._meta_cache[icao24]
        row = db.lookup_aircraft(con, icao24)
        m = dict(row) if row else {}
        self._meta_cache[icao24] = m
        return m

    # ---- main loop ----
    def run(self):
        self.load_from_db()
        con = db.connect()
        while not self._stop.is_set():
            t0 = time.time()
            try:
                if self.collecting and self.airport:
                    self._poll_once(con)
                    self.last_error = None
            except Exception as e:
                self.last_error = str(e)
            # sleep the remainder of the interval
            elapsed = time.time() - t0
            self._stop.wait(max(1.0, self.poll_sec - elapsed))
        con.close()

    def _poll_once(self, con):
        ap = self.airport
        data = opensky.fetch_states(ap["lat"], ap["lon"], self.radius_km)
        states = data.get("states") or []
        seen = set()
        for raw in states:
            st = opensky.parse_state(raw)
            if st["lat"] is None or st["lon"] is None:
                continue
            seen.add(st["icao24"])
            meta = self._meta(con, st["icao24"])
            biz = detector.is_business(meta.get("typecode"), st["category"], self.include_turboprops)
            if not biz:
                continue
            with self.lock:
                tr = self.tracks.get(st["icao24"])
                if not tr:
                    tr = detector.Track(st["icao24"], meta); self.tracks[st["icao24"]] = tr
                tr.biz = True
                event = detector.update(tr, st, ap)
            if event:
                self._record(con, tr, event, ap)
        # expire stale tracks
        cutoff = time.time() - 6*60
        with self.lock:
            for icao in list(self.tracks):
                tr = self.tracks[icao]
                if icao not in seen:
                    last_t = tr.samples[-1]["t"] if tr.samples else 0
                    if last_t < cutoff:
                        ev = detector.finalize_on_exit(tr)
                        if ev:
                            self._record(con, tr, ev, ap)
                        del self.tracks[icao]
        self.last_sync = detector.now_iso()

    def _record(self, con, tr, event, ap):
        if db.recent_duplicate(con, ap["icao"], tr.icao24, event):
            return
        s, m = tr.snapshot, tr.meta
        alts = [x["baro_alt"] for x in tr.samples if x["baro_alt"] is not None]
        rec = {
            "event": event, "detected_at": detector.now_iso(),
            "date_utc": time.strftime("%Y-%m-%d", time.gmtime()), "airport": ap["icao"],
            "icao24": tr.icao24, "callsign": s.get("callsign") or None,
            "registration": m.get("registration"), "typecode": m.get("typecode"),
            "model": m.get("model"), "manufacturer": m.get("manufacturer"),
            "operator": m.get("operator"), "serial": m.get("serial"), "built": m.get("built"),
            "origin_country": s.get("origin_country"), "category": s.get("category"),
            "squawk": s.get("squawk"), "lat": s.get("lat"), "lon": s.get("lon"),
            "baro_alt_m": s.get("baro_alt"), "geo_alt_m": s.get("geo_alt"),
            "velocity_ms": s.get("velocity"), "vertical_rate_ms": s.get("vrate"),
            "track_deg": s.get("track"),
            "max_alt_m": max(alts) if alts else None, "min_alt_m": min(alts) if alts else None,
            "first_seen": tr.first, "last_seen": tr.last,
            "closest_km": round(tr.min_dist, 2), "source": "live",
        }
        db.insert_flight(con, rec)

    def radar(self):
        with self.lock:
            out = []
            for tr in self.tracks.values():
                if not tr.snapshot:
                    continue
                s, m = tr.snapshot, tr.meta
                out.append({
                    "icao24": tr.icao24, "callsign": s.get("callsign"),
                    "registration": m.get("registration"), "typecode": m.get("typecode"),
                    "model": m.get("model"), "operator": m.get("operator"),
                    "phase": tr.phase, "dist_km": round(s.get("dist", 0), 1),
                    "agl_m": s.get("agl"), "velocity_ms": s.get("velocity"),
                })
            out.sort(key=lambda x: x["dist_km"])
            return out

    def status(self):
        return {
            "collecting": self.collecting,
            "airport": self.airport,
            "poll_sec": self.poll_sec,
            "radius_km": self.radius_km,
            "include_turboprops": self.include_turboprops,
            "last_sync": self.last_sync,
            "last_error": self.last_error,
            "tracking": len(self.tracks),
        }

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self):
        self._stop.set()
