"""Arrival/departure detection from successive state-vector samples, plus the
business-aircraft type classifier. Airport-agnostic: works from the selected
airport's coordinates and field elevation."""
import math, time

BIZJETS = set("""GLF2 GLF3 GLF4 GLF5 GLF6 GA5C GA6C GA7C GALX ASTR WW24 G150 G280 C750
CL30 CL35 CL60 CL64 CL65 GL5T GL7T GLEX GL8T
LJ23 LJ24 LJ25 LJ28 LJ31 LJ35 LJ36 LJ40 LJ45 LJ55 LJ60 LJ70 LJ75 LJ85
C500 C501 C510 C525 C526 C550 C551 C55B C560 C56X C650 C680 C68A C700 C25A C25B C25C C25M C25P J328
FA10 FA20 FA50 F2TH F900 FA7X FA8X FA6X
E50P E55P E545 E550 E135 E35L E145
H25A H25B H25C HA4T BE40 BE4W PRM1
PC24 HDJT EA50 SF50 EA55 FA90 NEXT""".split())

TURBOPROPS = set("PC12 TBM7 TBM8 TBM9 TBM BE20 B350 BE9L BE10 C441 P180 PAY3 PAY4 E120 SW4 B190".split())
LIGHT_CATEGORIES = {2, 3}

def is_business(typecode, category, include_turboprops):
    t = (typecode or "").upper().strip()
    if t and t in BIZJETS:
        return True
    if include_turboprops and t and t in TURBOPROPS:
        return True
    if t:
        return False
    # unknown type: provisional by ADS-B weight class (often absent in practice)
    return category in LIGHT_CATEGORIES

def haversine_km(la1, lo1, la2, lo2):
    R, d = 6371.0, math.pi/180
    a = math.sin((la2-la1)*d/2)**2 + math.cos(la1*d)*math.cos(la2*d)*math.sin((lo2-lo1)*d/2)**2
    return 2*R*math.asin(math.sqrt(a))

class Track:
    __slots__ = ("icao24","first","last","samples","was_high","was_near_ground",
                 "min_dist","recorded","biz","phase","snapshot","meta")
    def __init__(self, icao24, meta):
        self.icao24 = icao24
        self.meta = meta or {}
        self.first = self.last = now_iso()
        self.samples = []
        self.was_high = False
        self.was_near_ground = False
        self.min_dist = 9999.0
        self.recorded = None
        self.biz = False
        self.phase = "local"
        self.snapshot = None

def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

NEAR_KM = 8.0

def update(track, st, ap):
    """Add a sample; return event string if a movement is detected, else None."""
    dist = haversine_km(st["lat"], st["lon"], ap["lat"], ap["lon"])
    agl = (st["baro_alt"] - ap["elev_m"]) if st["baro_alt"] is not None else None
    track.last = now_iso()
    track.samples.append({"t": time.time(), "dist": dist, "agl": agl, "vrate": st["vrate"],
                          "on_ground": st["on_ground"], "baro_alt": st["baro_alt"],
                          "geo_alt": st["geo_alt"], "velocity": st["velocity"]})
    if len(track.samples) > 40:
        track.samples.pop(0)
    track.min_dist = min(track.min_dist, dist)
    if agl is not None and agl > 900:
        track.was_high = True
    if st["on_ground"] is True or (agl is not None and agl < 120 and dist < 6):
        track.was_near_ground = True

    phase = "local"
    if agl is not None and st["vrate"] is not None and dist < 30:
        if st["vrate"] < -1.2: phase = "inbound"
        elif st["vrate"] > 1.2: phase = "outbound"
    track.phase = phase
    track.snapshot = {**st, "dist": dist, "agl": agl}

    return _detect(track)

def _near(track):
    return track.min_dist < NEAR_KM

def _detect(track):
    if track.recorded or len(track.samples) < 2:
        return None
    a, b = track.samples[0], track.samples[-1]
    climbing = (b["vrate"] is not None and b["vrate"] > 1) and (b["agl"] is not None and b["agl"] > 250) and (b["dist"] > a["dist"])
    if track.was_near_ground and climbing and _near(track):
        track.recorded = "departure"; return "departure"
    arrived = (track.was_high and track.was_near_ground
               and (b["on_ground"] is True or (b["agl"] is not None and b["agl"] < 150))
               and _near(track) and (b["dist"] <= a["dist"] or b["dist"] < 6))
    if arrived:
        track.recorded = "arrival"; return "arrival"
    return None

def finalize_on_exit(track):
    if track.recorded or not _near(track) or len(track.samples) < 3:
        return None
    first, last = track.samples[0], track.samples[-1]
    if track.was_near_ground and last["agl"] is not None and first["agl"] is not None:
        if last["agl"] - first["agl"] > 400 and last["dist"] > first["dist"]:
            track.recorded = "departure"; return "departure"
        if track.was_high and last["agl"] < 400:
            track.recorded = "arrival"; return "arrival"
    return None
