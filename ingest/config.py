"""Central configuration. Every path and knob can be overridden with an env var."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("FWA_DATA_DIR", ROOT / "data"))
WAREHOUSE_PATH = Path(os.getenv("FWA_WAREHOUSE", DATA_DIR / "warehouse.duckdb"))
PUBLISH_DIR = Path(os.getenv("FWA_PUBLISH_DIR", DATA_DIR / "published"))
REGIONS_GEOJSON = ROOT / "ingest" / "reference" / "fi_regions.geojson"

# lon_min, lat_min, lon_max, lat_max (WGS84). Covers mainland Finland and Åland.
FINLAND_BBOX = (19.0, 59.4, 31.7, 70.2)

# H3 resolutions: res 5 (~250 km2 per cell) for interpolated weather,
# res 4 (~1,770 km2 per cell) for the aurora score, which needs one
# cloud-cover API call per cell.
H3_RES_WEATHER = 5
H3_RES_AURORA = 4

# --- Finnish Meteorological Institute (FMI) open data WFS -------------------
FMI_WFS_URL = os.getenv("FWA_FMI_WFS_URL", "https://opendata.fmi.fi/wfs")
FMI_OBS_QUERY = "fmi::observations::weather::simple"
FMI_STATIONS_QUERY = "fmi::ef::stations"
# FMI parameter code -> description. Units are in transform/seeds/fmi_parameters.csv
FMI_PARAMETERS = {
    "t2m": "air temperature",
    "ws_10min": "wind speed, 10 min mean",
    "wg_10min": "wind gust, 10 min max",
    "r_1h": "precipitation, 1 h sum",
    "snow_aws": "snow depth",
    "n_man": "cloud cover (octas)",
    "rh": "relative humidity",
    "p_sea": "sea level pressure",
}
FMI_MAX_SPAN_HOURS = 168  # FMI caps one observation request at 7 days
FMI_CHUNK_HOURS = int(os.getenv("FWA_FMI_CHUNK_HOURS", "3"))
FMI_OVERLAP_HOURS = 3  # re-read recent hours so late-arriving values are picked up
DEFAULT_BACKFILL_HOURS = int(os.getenv("FWA_BACKFILL_HOURS", "72"))

# --- NOAA Space Weather Prediction Center ------------------------------------
SWPC_BASE = os.getenv("FWA_SWPC_BASE", "https://services.swpc.noaa.gov")
SWPC_KP_OBSERVED = f"{SWPC_BASE}/products/noaa-planetary-k-index.json"
SWPC_KP_FORECAST = f"{SWPC_BASE}/products/noaa-planetary-k-index-forecast.json"
# Real-time solar wind (RTSW). Replaced the /products/solar-wind/*.json files in 2026 (NWS SCN 26-21).
SWPC_SOLAR_WIND_MAG = f"{SWPC_BASE}/json/rtsw/rtsw_mag_1m.json"
SWPC_SOLAR_WIND_PLASMA = f"{SWPC_BASE}/json/rtsw/rtsw_wind_1m.json"

# --- Open-Meteo (cloud cover forecast for every aurora cell) ----------------
OPENMETEO_URL = os.getenv("FWA_OPENMETEO_URL", "https://api.open-meteo.com/v1/forecast")
OPENMETEO_BATCH = 50  # locations per request
OPENMETEO_PAST_HOURS = 12
OPENMETEO_FORECAST_HOURS = 48

HTTP_TIMEOUT_S = 60
USER_AGENT = "finland-weather-aurora/1.0 (+https://github.com/munyingi/finland-weather-aurora)"
