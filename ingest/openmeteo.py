"""Open-Meteo hourly cloud cover for every aurora grid cell (no API key needed).

Locations are sent in batches; the API returns one object per location in
request order, so rows are mapped back to cells by position.
"""

from __future__ import annotations

import json
from datetime import datetime

from . import config
from .http import Client


def parse_cloud(payload: bytes, cell_ids: list[str]) -> list[dict]:
    data = json.loads(payload)
    if isinstance(data, dict):  # single-location responses are a bare object
        data = [data]
    if len(data) != len(cell_ids):
        raise ValueError(f"Open-Meteo returned {len(data)} locations for {len(cell_ids)} requested")
    rows = []
    for cell_id, loc in zip(cell_ids, data, strict=True):
        hourly = loc.get("hourly", {})
        times = hourly.get("time", [])
        total = hourly.get("cloud_cover", [None] * len(times))
        low = hourly.get("cloud_cover_low", [None] * len(times))
        for t, cc, cl in zip(times, total, low, strict=False):
            if cc is None:
                continue
            rows.append(
                {
                    "cell_id": cell_id,
                    "valid_at": datetime.fromisoformat(t),
                    "cloud_cover_pct": float(cc),
                    "cloud_cover_low_pct": None if cl is None else float(cl),
                }
            )
    return rows


def fetch_cloud(client: Client, cells: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for i in range(0, len(cells), config.OPENMETEO_BATCH):
        batch = cells[i : i + config.OPENMETEO_BATCH]
        payload = client.get(
            config.OPENMETEO_URL,
            {
                "latitude": ",".join(f"{c['lat']:.4f}" for c in batch),
                "longitude": ",".join(f"{c['lon']:.4f}" for c in batch),
                "hourly": "cloud_cover,cloud_cover_low",
                "past_hours": config.OPENMETEO_PAST_HOURS,
                "forecast_hours": config.OPENMETEO_FORECAST_HOURS,
                "timezone": "GMT",
            },
        )
        rows.extend(parse_cloud(payload, [c["cell_id"] for c in batch]))
    return rows
