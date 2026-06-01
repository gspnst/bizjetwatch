"""OpenSky live state-vector access. Server-side, so OAuth and CORS are non-issues.
Anonymous works (rate-limited); client credentials lift the limits."""
import json, time, math, urllib.request, urllib.parse, urllib.error
from . import config

API = "https://opensky-network.org/api"
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
_token = {"value": None, "exp": 0}

def bbox(lat, lon, radius_km):
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)

def _get_token():
    if not config.OPENSKY_CLIENT_ID or not config.OPENSKY_CLIENT_SECRET:
        return None
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": config.OPENSKY_CLIENT_ID,
        "client_secret": config.OPENSKY_CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.load(r)
    _token["value"] = j["access_token"]
    _token["exp"] = time.time() + j.get("expires_in", 1800)
    return _token["value"]

def fetch_states(lat, lon, radius_km):
    la1, lo1, la2, lo2 = bbox(lat, lon, radius_km)
    qs = urllib.parse.urlencode({"lamin": round(la1,4), "lomin": round(lo1,4),
                                 "lamax": round(la2,4), "lomax": round(lo2,4)})
    headers = {"User-Agent": "bizjet-watch"}
    try:
        tok = _get_token()
        if tok:
            headers["Authorization"] = "Bearer " + tok
    except Exception:
        pass
    req = urllib.request.Request(f"{API}/states/all?{qs}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RuntimeError("rate limited (429)")
        raise RuntimeError(f"opensky {e.code}")

# state vector field order (subset we use)
def parse_state(s):
    return {
        "icao24": s[0], "callsign": (s[1] or "").strip(), "origin_country": s[2],
        "lon": s[5], "lat": s[6], "baro_alt": s[7], "on_ground": s[8],
        "velocity": s[9], "track": s[10], "vrate": s[11], "geo_alt": s[13],
        "squawk": s[14], "category": s[17] if len(s) > 17 else None,
    }
