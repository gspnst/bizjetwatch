# BizJet Watch

A small, self-hostable tracker that records **business-jet arrivals and departures**
at any EU international airport. Point it at an airport, leave it running on a
Raspberry Pi, and it builds a persistent log of every business-aviation movement
it sees — aircraft type, registration, operator, and the flight state at the moment
of detection.

It runs as a single Python process: a background collector that polls live ADS-B
data and writes to a SQLite database, plus a clean web interface to browse what it
has captured. Because collection happens server-side, it keeps working whether or
not a browser is open.

_A clean, light web UI: live "on radar" panel, today's arrival/departure counts, and a searchable, persistent movement log with full per-flight detail._

## How it works

1. A background loop polls the [OpenSky Network](https://opensky-network.org/) for
   aircraft inside a radius around the selected airport.
2. State vectors carry no aircraft type, so each aircraft's 24-bit ICAO address is
   matched against OpenSky's downloadable **aircraft database** (imported once into
   SQLite) to resolve type, registration and operator.
3. Aircraft whose ICAO type designator is a known business jet (Gulfstream,
   Bombardier, Citation, Falcon, Phenom/Praetor, Learjet, HondaJet, PC-24, …;
   optionally business turboprops) are tracked across polls.
4. A trajectory heuristic (altitude, vertical rate, distance, ground state)
   classifies each movement as an **arrival** or **departure** and writes a record.

## Quick start

Any machine with Python 3.9+:

```bash
git clone https://github.com/<you>/bizjet-watch.git
cd bizjet-watch
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:8000/`. On first run it downloads the aircraft database once
(a few dozen MB, cached in SQLite). Pick your airport from the dropdown and it
starts collecting.

## Raspberry Pi (persistent service)

```bash
git clone https://github.com/<you>/bizjet-watch.git
cd bizjet-watch
./deploy/install.sh
```

This creates a virtualenv, installs a `systemd` service, and enables it on boot.
Turn collection on/off by starting/stopping the service:

```bash
sudo systemctl start bizjet-watch    # on
sudo systemctl stop  bizjet-watch    # off
journalctl -u bizjet-watch -f        # live logs
```

The web UI also has a **Pause/Resume** button that halts collection without
stopping the service.

## Configuration

Runtime options (airport, poll interval, radius, turboprops) are set from the web
UI and stored in the database. Environment variables cover the rest:

| Variable | Default | Purpose |
|---|---|---|
| `BIZJET_PORT` | `8000` | web port |
| `BIZJET_AIRPORT` | `LKPR` | airport on first launch |
| `BIZJET_RADIUS_KM` | `45` | airspace box radius |
| `BIZJET_POLL` | `12` | seconds between polls |
| `OPENSKY_CLIENT_ID` / `OPENSKY_CLIENT_SECRET` | — | optional OpenSky OAuth to lift anonymous rate limits |

Anonymous OpenSky access works but is rate-limited; if you see `429` errors,
increase the poll interval or add OAuth credentials (free OpenSky account).

## Data

- **Flights** and the **aircraft database** live in `bizjet.db` (SQLite). Export the
  log at any time via the *Export CSV* button or `GET /api/export.csv`.
- The EU airport list (`data/airports.csv`) is generated from the public-domain
  [OurAirports](https://ourairports.com/data/) dataset; regenerate it with
  `python tools/build_airports.py`.

## API

`GET /api/airports` · `GET /api/status` · `GET /api/stats` · `GET /api/radar` ·
`GET /api/flights?event=&q=&limit=&offset=` · `POST /api/airport {icao}` ·
`POST /api/settings {poll_sec,radius_km,include_turboprops,collecting}` ·
`GET /api/export.csv`

## Limitations & honesty

- Arrival/departure direction is **inferred** from the live state stream, not from
  filed flight plans, so very fast or very low passes can occasionally be missed or
  misclassified.
- Type identification depends on the OpenSky aircraft database, which is
  community-maintained and updated irregularly — a brand-new or obscure airframe may
  be missing and slip past the filter. Type codes for existing aircraft are stable.
- Coverage follows OpenSky's ADS-B receiver coverage (very good across Europe).
- Scope is currently **EU-27 international airports**; extending to other regions is
  a one-line change to the country filter in `tools/build_airports.py`.

## Contributing

Issues and PRs welcome — especially additions to the business-jet type list
(`bizjet/detector.py`), detection-heuristic improvements, and airport-coverage
extensions. Run the project locally with `python app.py` and it reloads on restart.

## License

MIT — see [LICENSE](LICENSE). Flight data © OpenSky Network; aircraft and airport
metadata from OpenSky and OurAirports under their respective terms.
