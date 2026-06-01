"""Configuration. Defaults can be overridden by environment variables.
Runtime-changeable settings (airport, poll interval, radius, turboprops) live in
the database `settings` table and are editable from the web UI."""
import os

HOST = os.environ.get("BIZJET_HOST", "0.0.0.0")
PORT = int(os.environ.get("BIZJET_PORT", "8000"))
DB_PATH = os.environ.get("BIZJET_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bizjet.db"))
AIRPORTS_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "airports.csv")

# OpenSky aircraft database (icao24 -> type). Public, unlicensed, "as is".
AIRCRAFT_CSV_URL = os.environ.get("BIZJET_ACDB_URL", "https://opensky-network.org/datasets/metadata/aircraftDatabase.csv")

# Optional OpenSky OAuth2 client credentials (lifts anonymous rate limits).
OPENSKY_CLIENT_ID = os.environ.get("OPENSKY_CLIENT_ID", "")
OPENSKY_CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET", "")

# Defaults used the very first time the DB is created.
DEFAULT_AIRPORT = os.environ.get("BIZJET_AIRPORT", "LKPR")
DEFAULT_POLL_SEC = int(os.environ.get("BIZJET_POLL", "12"))
DEFAULT_RADIUS_KM = float(os.environ.get("BIZJET_RADIUS_KM", "45"))
DEFAULT_INCLUDE_TURBOPROPS = os.environ.get("BIZJET_TURBOPROPS", "0") == "1"
