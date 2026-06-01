#!/usr/bin/env python3
"""Generate data/airports.csv: EU international airports, from the public-domain
OurAirports dataset (https://ourairports.com/data/, public domain).

Usage: python3 tools/build_airports.py [path-to-airports.csv]
Filters: EU-27 countries, type in {large_airport, medium_airport},
scheduled_service == yes, valid 4-letter ICAO. Elevation converted to metres.
"""
import csv, sys, os

EU = {"AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE",
      "IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE"}
SRC = sys.argv[1] if len(sys.argv) > 1 else "/tmp/airports_raw.csv"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "airports.csv")

rows = []
with open(SRC, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["iso_country"] not in EU:
            continue
        if r["type"] not in ("large_airport", "medium_airport"):
            continue
        if r["scheduled_service"] != "yes":
            continue
        icao = (r.get("icao_code") or r.get("ident") or "").strip().upper()
        if len(icao) != 4 or not icao.isalpha():
            continue
        try:
            lat = float(r["latitude_deg"]); lon = float(r["longitude_deg"])
        except ValueError:
            continue
        try:
            elev_m = round(float(r["elevation_ft"]) * 0.3048)
        except (ValueError, KeyError):
            elev_m = 0
        rows.append({
            "icao": icao,
            "name": r["name"].strip(),
            "city": (r.get("municipality") or "").strip(),
            "country": r["iso_country"],
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "elev_m": elev_m,
            "type": "L" if r["type"] == "large_airport" else "M",
            "iata": (r.get("iata_code") or "").strip(),
        })

# large airports first, then by country, then name
rows.sort(key=lambda x: (x["type"] != "L", x["country"], x["name"]))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["icao","name","city","country","lat","lon","elev_m","type","iata"])
    w.writeheader()
    w.writerows(rows)

print(f"wrote {len(rows)} airports -> {OUT}")
print(f"  large: {sum(1 for x in rows if x['type']=='L')}, medium: {sum(1 for x in rows if x['type']=='M')}")
# sanity: show LKPR
for x in rows:
    if x["icao"] == "LKPR":
        print("  LKPR:", x)
