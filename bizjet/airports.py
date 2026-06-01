"""EU international airport directory loaded from data/airports.csv."""
import csv
from . import config

_BY_ICAO = {}
_LIST = []

def load():
    global _BY_ICAO, _LIST
    _BY_ICAO, _LIST = {}, []
    with open(config.AIRPORTS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            a = {
                "icao": r["icao"], "name": r["name"], "city": r["city"],
                "country": r["country"], "lat": float(r["lat"]), "lon": float(r["lon"]),
                "elev_m": int(r["elev_m"]), "type": r["type"], "iata": r["iata"],
            }
            _BY_ICAO[a["icao"]] = a
            _LIST.append(a)
    return _LIST

def all_airports():
    return _LIST

def get(icao):
    return _BY_ICAO.get((icao or "").upper())
