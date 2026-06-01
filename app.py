#!/usr/bin/env python3
"""bizjet-watch — business-jet movement tracker for EU international airports.

Single process: a Flask web app that serves the UI + JSON API, and a background
poller thread that collects data into SQLite whenever the service is running.

Run:   python3 app.py
Then:  http://<pi-ip>:8000/
"""
import os, json, time
from flask import Flask, jsonify, request, send_from_directory, Response
from bizjet import config, db, airports, aircraftdb
from bizjet.poller import Poller

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
app = Flask(__name__, static_folder=None)
poller = Poller()

# ---- pages --------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")

@app.route("/<path:fn>")
def asset(fn):
    return send_from_directory(WEB_DIR, fn)

# ---- API ----------------------------------------------------------------------
@app.route("/api/airports")
def api_airports():
    return jsonify(airports.all_airports())

@app.route("/api/status")
def api_status():
    con = db.connect()
    ap = poller.airport or {}
    st = poller.status()
    st["aircraft_db"] = {**aircraftdb.STATE, "count": db.aircraft_count(con)}
    con.close()
    return jsonify(st)

@app.route("/api/stats")
def api_stats():
    con = db.connect()
    ap = poller.airport or {"icao": config.DEFAULT_AIRPORT}
    out = db.stats(con, ap["icao"], time.strftime("%Y-%m-%d", time.gmtime()))
    con.close()
    return jsonify(out)

@app.route("/api/radar")
def api_radar():
    return jsonify(poller.radar())

@app.route("/api/flights")
def api_flights():
    con = db.connect()
    ap = poller.airport or {"icao": config.DEFAULT_AIRPORT}
    rows = db.query_flights(
        con, airport=request.args.get("airport", ap["icao"]),
        event=request.args.get("event"), q=request.args.get("q"),
        limit=min(500, int(request.args.get("limit", 100))),
        offset=int(request.args.get("offset", 0)))
    con.close()
    return jsonify(rows)

@app.route("/api/airport", methods=["POST"])
def api_set_airport():
    icao = (request.json or {}).get("icao", "")
    if poller.set_airport(icao):
        return jsonify({"ok": True, "airport": poller.airport})
    return jsonify({"ok": False, "error": "unknown airport"}), 400

@app.route("/api/settings", methods=["POST"])
def api_settings():
    b = request.json or {}
    poller.set_options(
        poll_sec=b.get("poll_sec"), radius_km=b.get("radius_km"),
        include_turboprops=b.get("include_turboprops"), collecting=b.get("collecting"))
    return jsonify({"ok": True, "status": poller.status()})

@app.route("/api/export.csv")
def api_export_csv():
    con = db.connect()
    ap = poller.airport or {"icao": config.DEFAULT_AIRPORT}
    rows = db.query_flights(con, airport=request.args.get("airport", ap["icao"]), limit=100000)
    con.close()
    import io, csv as _csv
    buf = io.StringIO()
    if rows:
        w = _csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=bizjet-flights.csv"})

def main():
    db.init()
    airports.load()
    aircraftdb.start_background()      # import aircraft DB if needed (one-time)
    poller.start()
    print(f"  bizjet-watch on http://{config.HOST}:{config.PORT}/  (airport {poller.airport['icao'] if poller.airport else '?'})")
    app.run(host=config.HOST, port=config.PORT, threaded=True)

if __name__ == "__main__":
    main()
