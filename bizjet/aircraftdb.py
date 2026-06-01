"""Maintains the icao24 -> aircraft-type table inside SQLite.

OpenSky state vectors carry no aircraft type, so type identification depends on
mapping the 24-bit ICAO address against OpenSky's downloadable aircraft database.
We import it into SQLite once (indexed by icao24); lookups are then cheap and
offline -- important on a Raspberry Pi with limited RAM."""
import csv, io, os, gzip, time, threading, urllib.request
from . import config, db

STATE = {"ready": False, "importing": False, "count": 0, "error": None}
_lock = threading.Lock()

def _stream_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "bizjet-watch"})
    raw = urllib.request.urlopen(req, timeout=180).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return io.StringIO(raw.decode("utf-8", "replace"))

def ensure_imported(force=False):
    """Import the aircraft DB into SQLite if the table is empty. Idempotent."""
    with _lock:
        con = db.connect()
        have = db.aircraft_count(con)
        if have > 0 and not force:
            STATE.update(ready=True, count=have)
            con.close(); return
        STATE.update(importing=True, error=None)
        try:
            print("  [acdb] downloading aircraft database (one-time)...")
            f = _stream_csv(config.AIRCRAFT_CSV_URL)
            reader = csv.DictReader(f)
            batch, n = [], 0
            con.execute("DELETE FROM aircraft")
            for row in reader:
                hexid = (row.get("icao24") or "").strip().lower()
                if not hexid:
                    continue
                batch.append((
                    hexid, row.get("registration","").strip() or None,
                    (row.get("typecode","") or "").strip().upper() or None,
                    row.get("model","").strip() or None,
                    row.get("manufacturername","").strip() or None,
                    (row.get("operator","") or row.get("operatoricao","")).strip() or None,
                    row.get("owner","").strip() or None,
                    row.get("serialnumber","").strip() or None,
                    row.get("built","").strip() or None,
                    row.get("icaoaircrafttype","").strip() or None,
                ))
                if len(batch) >= 5000:
                    con.executemany("INSERT OR REPLACE INTO aircraft VALUES(?,?,?,?,?,?,?,?,?,?)", batch)
                    n += len(batch); batch = []
            if batch:
                con.executemany("INSERT OR REPLACE INTO aircraft VALUES(?,?,?,?,?,?,?,?,?,?)", batch)
                n += len(batch)
            con.commit()
            STATE.update(ready=True, count=n)
            print(f"  [acdb] ready - {n:,} airframes indexed")
        except Exception as e:
            STATE["error"] = str(e)
            print(f"  [acdb] FAILED: {e}\n  [acdb] type identification limited until this succeeds.")
        finally:
            STATE["importing"] = False
            con.close()

def start_background():
    threading.Thread(target=ensure_imported, daemon=True).start()
