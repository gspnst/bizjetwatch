"""SQLite persistence. WAL mode lets the poller thread write while the web
layer reads. Each thread opens its own connection."""
import sqlite3, json, time
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS flights(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event TEXT, detected_at TEXT, date_utc TEXT, airport TEXT,
  icao24 TEXT, callsign TEXT, registration TEXT, typecode TEXT, model TEXT,
  manufacturer TEXT, operator TEXT, serial TEXT, built TEXT,
  origin_country TEXT, category INTEGER, squawk TEXT,
  lat REAL, lon REAL, baro_alt_m REAL, geo_alt_m REAL,
  velocity_ms REAL, vertical_rate_ms REAL, track_deg REAL,
  max_alt_m REAL, min_alt_m REAL, first_seen TEXT, last_seen TEXT,
  closest_km REAL, source TEXT
);
CREATE INDEX IF NOT EXISTS idx_flights_detected ON flights(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_flights_airport  ON flights(airport);
CREATE INDEX IF NOT EXISTS idx_flights_event    ON flights(event);

CREATE TABLE IF NOT EXISTS aircraft(
  icao24 TEXT PRIMARY KEY, registration TEXT, typecode TEXT, model TEXT,
  manufacturer TEXT, operator TEXT, owner TEXT, serial TEXT, built TEXT, icaotype TEXT
);

CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""

def connect():
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA busy_timeout=30000")
    return con

def init():
    con = connect()
    con.executescript(SCHEMA)
    con.commit()
    # seed defaults if missing
    defaults = {
        "airport": config.DEFAULT_AIRPORT,
        "poll_sec": str(config.DEFAULT_POLL_SEC),
        "radius_km": str(config.DEFAULT_RADIUS_KM),
        "include_turboprops": "1" if config.DEFAULT_INCLUDE_TURBOPROPS else "0",
        "collecting": "1",
    }
    for k, v in defaults.items():
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    con.commit()
    con.close()

# ---- settings -----------------------------------------------------------------
def get_setting(con, key, default=None):
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_setting(con, key, value):
    con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))
    con.commit()

def all_settings(con):
    return {r["key"]: r["value"] for r in con.execute("SELECT key,value FROM settings")}

# ---- aircraft database --------------------------------------------------------
def aircraft_count(con):
    return con.execute("SELECT COUNT(*) c FROM aircraft").fetchone()["c"]

def lookup_aircraft(con, icao24):
    return con.execute("SELECT * FROM aircraft WHERE icao24=?", ((icao24 or "").lower(),)).fetchone()

# ---- flights ------------------------------------------------------------------
FLIGHT_COLS = ["event","detected_at","date_utc","airport","icao24","callsign","registration",
    "typecode","model","manufacturer","operator","serial","built","origin_country","category",
    "squawk","lat","lon","baro_alt_m","geo_alt_m","velocity_ms","vertical_rate_ms","track_deg",
    "max_alt_m","min_alt_m","first_seen","last_seen","closest_km","source"]

def recent_duplicate(con, airport, icao24, event, within_sec=1800):
    """True if we already logged this aircraft+event at this airport very recently."""
    cutoff = time.time() - within_sec
    row = con.execute(
        "SELECT detected_at FROM flights WHERE airport=? AND icao24=? AND event=? "
        "ORDER BY id DESC LIMIT 1", (airport, icao24, event)).fetchone()
    if not row:
        return False
    try:
        import datetime
        t = datetime.datetime.fromisoformat(row["detected_at"].replace("Z","+00:00")).timestamp()
        return t > cutoff
    except Exception:
        return False

def insert_flight(con, rec):
    cols = ",".join(FLIGHT_COLS)
    ph = ",".join("?" for _ in FLIGHT_COLS)
    con.execute(f"INSERT INTO flights({cols}) VALUES({ph})", [rec.get(c) for c in FLIGHT_COLS])
    con.commit()

def query_flights(con, airport=None, event=None, q=None, limit=100, offset=0):
    where, args = [], []
    if airport: where.append("airport=?"); args.append(airport)
    if event in ("arrival","departure"): where.append("event=?"); args.append(event)
    if q:
        like = f"%{q.lower()}%"
        where.append("(LOWER(callsign) LIKE ? OR LOWER(registration) LIKE ? OR LOWER(typecode) LIKE ? OR LOWER(model) LIKE ? OR LOWER(operator) LIKE ? OR icao24 LIKE ?)")
        args += [like, like, like, like, like, like]
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = con.execute(f"SELECT * FROM flights {wsql} ORDER BY id DESC LIMIT ? OFFSET ?",
                       args + [limit, offset]).fetchall()
    return [dict(r) for r in rows]

def stats(con, airport, date_utc):
    arr = con.execute("SELECT COUNT(*) c FROM flights WHERE airport=? AND event='arrival' AND date_utc=?", (airport, date_utc)).fetchone()["c"]
    dep = con.execute("SELECT COUNT(*) c FROM flights WHERE airport=? AND event='departure' AND date_utc=?", (airport, date_utc)).fetchone()["c"]
    tot = con.execute("SELECT COUNT(*) c FROM flights WHERE airport=?", (airport,)).fetchone()["c"]
    return {"arrivals_today": arr, "departures_today": dep, "total": tot}
