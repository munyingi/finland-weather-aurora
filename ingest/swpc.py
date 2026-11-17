"""NOAA SWPC space weather: planetary Kp (observed + 3-day forecast) and real-time solar wind.

SWPC has served these products both as a header row followed by value rows and
as a list of objects. `parse_table` accepts either shape.
"""

from __future__ import annotations

import json
from datetime import datetime

from . import config
from .http import Client


def _to_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_time(v: str) -> datetime:
    s = str(v).strip().replace("Z", "").replace("T", " ")
    s = s.split(".")[0]
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if len(s) > 16 else datetime.strptime(s, "%Y-%m-%d %H:%M")


def parse_table(payload: bytes) -> list[dict]:
    data = json.loads(payload)
    if not data:
        return []
    if isinstance(data[0], dict):
        return [{str(k).lower(): v for k, v in row.items()} for row in data]
    header = [str(h).lower() for h in data[0]]
    return [dict(zip(header, row, strict=False)) for row in data[1:]]


def parse_kp(payload: bytes, product: str) -> list[dict]:
    rows = []
    for r in parse_table(payload):
        kp = _to_float(r.get("kp", r.get("kp_index", r.get("estimated_kp"))))
        if r.get("time_tag") is None or kp is None:
            continue
        status = str(r.get("observed", "observed")).lower() if product == "forecast" else "observed"
        rows.append(
            {
                "block_start": _parse_time(r["time_tag"]),
                "product": product,
                "kp": kp,
                "status": status,
                "noaa_scale": r.get("noaa_scale"),
            }
        )
    return rows


def _active_rows(payload: bytes) -> list[dict]:
    """RTSW files can list several spacecraft per minute; keep the one forecasters mark active."""
    rows = [r for r in parse_table(payload) if r.get("time_tag") is not None]
    if any("active" in r for r in rows):
        rows = [r for r in rows if r.get("active") in (True, "true", "True", 1)]
    return rows


def parse_solar_wind(mag_payload: bytes, plasma_payload: bytes) -> list[dict]:
    """Merge magnetometer and plasma minutes. Accepts both the RTSW field names
    (proton_speed, proton_density) and the retired product names (speed, density)."""
    merged: dict[datetime, dict] = {}
    for r in _active_rows(mag_payload):
        t = _parse_time(r["time_tag"])
        merged.setdefault(t, {"observed_at": t})
        merged[t].update({"bz_gsm_nt": _to_float(r.get("bz_gsm")), "bt_nt": _to_float(r.get("bt"))})
    for r in _active_rows(plasma_payload):
        t = _parse_time(r["time_tag"])
        merged.setdefault(t, {"observed_at": t})
        merged[t].update(
            {
                "speed_kms": _to_float(r.get("proton_speed", r.get("speed"))),
                "density_cm3": _to_float(r.get("proton_density", r.get("density"))),
            }
        )
    cols = ("observed_at", "bz_gsm_nt", "bt_nt", "speed_kms", "density_cm3")
    return [{c: row.get(c) for c in cols} for row in sorted(merged.values(), key=lambda x: x["observed_at"])]


def fetch_kp(client: Client) -> list[dict]:
    observed = parse_kp(client.get(config.SWPC_KP_OBSERVED), "observed")
    forecast = parse_kp(client.get(config.SWPC_KP_FORECAST), "forecast")
    return observed + forecast


def fetch_solar_wind(client: Client) -> list[dict]:
    return parse_solar_wind(client.get(config.SWPC_SOLAR_WIND_MAG), client.get(config.SWPC_SOLAR_WIND_PLASMA))
