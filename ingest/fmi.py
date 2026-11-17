"""FMI open data WFS: station metadata and hourly weather observations for all of Finland.

Parsing matches on XML local names, not full namespace URIs, so a namespace
version bump on FMI's side does not silently return zero rows.
"""

from __future__ import annotations

import io
import logging
import math
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

from . import config
from .http import Client

log = logging.getLogger(__name__)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def position_key(lat: float, lon: float) -> str:
    """Stable join key between observation points and station metadata."""
    return f"{lat:.4f},{lon:.4f}"


def _parse_pos(text: str) -> tuple[float, float]:
    lat_s, lon_s = text.split()[:2]
    return float(lat_s), float(lon_s)


def _parse_time(text: str) -> datetime:
    # FMI returns ISO 8601 UTC, e.g. 2026-11-17T18:00:00Z
    return datetime.fromisoformat(text.strip().replace("Z", "+00:00")).astimezone(UTC).replace(tzinfo=None)


def parse_observations(payload: bytes) -> list[dict]:
    """Parse a BsWfs 'simple' feature collection into long-format rows."""
    rows: list[dict] = []
    for _, elem in ET.iterparse(io.BytesIO(payload), events=("end",)):
        if _local(elem.tag) != "BsWfsElement":
            continue
        rec: dict = {}
        for child in elem.iter():
            name = _local(child.tag)
            if name == "pos" and child.text:
                rec["lat"], rec["lon"] = _parse_pos(child.text)
            elif name == "Time" and child.text:
                rec["observed_at"] = _parse_time(child.text)
            elif name == "ParameterName" and child.text:
                rec["parameter"] = child.text.strip()
            elif name == "ParameterValue" and child.text is not None:
                rec["raw_value"] = child.text.strip()
        elem.clear()
        if not {"lat", "lon", "observed_at", "parameter", "raw_value"} <= rec.keys():
            continue
        try:
            value = float(rec["raw_value"])
        except ValueError:
            continue
        if math.isnan(value):  # FMI encodes missing as NaN
            continue
        rows.append(
            {
                "position_key": position_key(rec["lat"], rec["lon"]),
                "station_lat": rec["lat"],
                "station_lon": rec["lon"],
                "observed_at": rec["observed_at"],
                "parameter": rec["parameter"],
                "value": value,
            }
        )
    return rows


def parse_stations(payload: bytes) -> list[dict]:
    """Parse EnvironmentalMonitoringFacility elements from fmi::ef::stations."""
    rows: list[dict] = []
    for _, elem in ET.iterparse(io.BytesIO(payload), events=("end",)):
        if _local(elem.tag) != "EnvironmentalMonitoringFacility":
            continue
        rec: dict = {"networks": []}
        for child in elem.iter():
            name = _local(child.tag)
            code_space = child.attrib.get("codeSpace", "")
            if name == "identifier" and "fmisid" in code_space and child.text:
                rec["fmisid"] = int(child.text.strip())
            elif name == "name" and child.text:
                if code_space.endswith("/name"):
                    rec["station_name"] = child.text.strip()
                elif code_space.endswith("/region"):
                    rec["municipality"] = child.text.strip()
            elif name == "pos" and child.text and "lat" not in rec:
                rec["lat"], rec["lon"] = _parse_pos(child.text)
            elif name == "beginPosition" and child.text:
                rec["active_from"] = _parse_time(child.text)
            elif name == "endPosition":
                rec["active_to"] = _parse_time(child.text) if child.text else None
            elif name == "belongsTo":
                title = next((v for k, v in child.attrib.items() if _local(k) == "title"), None)
                if title:
                    rec["networks"].append(title)
        elem.clear()
        if not {"fmisid", "lat", "lon"} <= rec.keys():
            continue
        rows.append(
            {
                "fmisid": rec["fmisid"],
                "station_name": rec.get("station_name"),
                "municipality": rec.get("municipality"),
                "lat": rec["lat"],
                "lon": rec["lon"],
                "position_key": position_key(rec["lat"], rec["lon"]),
                "networks": "; ".join(sorted(set(rec["networks"]))),
                "active_from": rec.get("active_from"),
                "active_to": rec.get("active_to"),
            }
        )
    return rows


def _bbox_param() -> str:
    lon_min, lat_min, lon_max, lat_max = config.FINLAND_BBOX
    return f"{lon_min},{lat_min},{lon_max},{lat_max},epsg::4326"


def fetch_stations(client: Client) -> list[dict]:
    payload = client.get(
        config.FMI_WFS_URL,
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "getFeature",
            "storedquery_id": config.FMI_STATIONS_QUERY,
        },
    )
    rows = parse_stations(payload)
    lon_min, lat_min, lon_max, lat_max = config.FINLAND_BBOX
    return [r for r in rows if lat_min <= r["lat"] <= lat_max and lon_min <= r["lon"] <= lon_max]


def time_windows(start: datetime, end: datetime, chunk_hours: int) -> list[tuple[datetime, datetime]]:
    """Split [start, end) into chunks; FMI rejects oversized requests."""
    if end <= start:
        return []
    windows = []
    cursor = start
    step = timedelta(hours=chunk_hours)
    while cursor < end:
        nxt = min(cursor + step, end)
        windows.append((cursor, nxt))
        cursor = nxt
    return windows


def fetch_observations(
    client: Client,
    start: datetime,
    end: datetime,
    chunk_hours: int = config.FMI_CHUNK_HOURS,
) -> list[dict]:
    max_span = timedelta(hours=config.FMI_MAX_SPAN_HOURS)
    if end - start > max_span:
        log.warning("Requested span exceeds FMI's 168 h limit; clipping start")
        start = end - max_span
    rows: list[dict] = []
    for w_start, w_end in time_windows(start, end, chunk_hours):
        payload = client.get(
            config.FMI_WFS_URL,
            {
                "service": "WFS",
                "version": "2.0.0",
                "request": "getFeature",
                "storedquery_id": config.FMI_OBS_QUERY,
                "bbox": _bbox_param(),
                "starttime": w_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                # endtime is inclusive at FMI; step back one second to avoid double-reading the boundary hour
                "endtime": (w_end - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "timestep": "60",
                "parameters": ",".join(config.FMI_PARAMETERS),
            },
        )
        chunk = parse_observations(payload)
        log.info("FMI %s -> %s: %d values", w_start, w_end, len(chunk))
        rows.extend(chunk)
    return rows
