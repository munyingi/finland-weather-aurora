"""Export the marts the dashboard needs to small Parquet files plus a health.json.

The scheduled workflow pushes these to the repo's `data` branch, and the
Streamlit app reads them from there, so the app never touches the warehouse.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from . import config

EXPORTS = {
    "aurora_cells": """
        select cell_id, valid_at, lat, lon, region_name, kp, kp_status, kp_effective, bz_mean_nt,
               speed_mean_kms, sun_altitude_deg, cloud_cover_pct, magnetic_latitude_deg,
               geomagnetic_chance, darkness_factor, clear_sky_factor, aurora_score, aurora_category
        from marts.fct_aurora_cell_hourly
        where valid_at >= (select max(valid_at) from marts.fct_aurora_cell_hourly) - interval 60 hour
    """,
    "aurora_tonight": "select * from marts.mart_aurora_tonight order by spot_rank",
    "aurora_spots_hourly": """
        select spot_name, region_name, valid_at, valid_at_local, kp, cloud_cover_pct, sun_altitude_deg,
               aurora_score, aurora_category
        from marts.mart_aurora_spots_hourly
        where valid_at >= (select max(valid_at) from marts.mart_aurora_spots_hourly) - interval 60 hour
    """,
    "space_weather_hourly": """
        select * from intermediate.int_space_weather_hourly
        where hour_at >= (select max(hour_at) from intermediate.int_space_weather_hourly) - interval 7 day
    """,
    "weather_cells": """
        select w.*, c.lat, c.lon, c.region_name
        from marts.fct_weather_cell_hourly as w
        join marts.dim_cells as c using (cell_id)
        where w.observed_at >= (select max(observed_at) from marts.fct_weather_cell_hourly) - interval 47 hour
    """,
    "region_daily": """
        select * from marts.fct_weather_region_daily
        where local_date >= (select max(local_date) from marts.fct_weather_region_daily) - interval 30 day
    """,
    "weather_events": """
        select * from marts.fct_weather_events
        where local_date >= (select max(local_date) from marts.fct_weather_events) - interval 30 day
        order by local_date desc, severity
    """,
    "stations": "select * from marts.dim_stations",
    "pipeline_health": "select * from marts.mart_pipeline_health order by source",
}


def publish(out_dir: Path | str | None = None, warehouse: Path | str | None = None, mode: str = "live") -> dict:
    out = Path(out_dir or config.PUBLISH_DIR)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(warehouse or config.WAREHOUSE_PATH), read_only=True)
    counts = {}
    for name, sql in EXPORTS.items():
        target = out / f"{name}.parquet"
        con.execute(f"copy ({sql}) to '{target.as_posix()}' (format parquet, compression zstd)")
        counts[name] = con.execute(f"select count(*) from '{target.as_posix()}'").fetchone()[0]
    generated = con.execute("select cast(timezone('UTC', now()) as timestamp)").fetchone()[0]
    manifest = {"generated_at_utc": generated.isoformat(timespec="seconds"), "mode": mode, "row_counts": counts}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    con.close()
    return manifest
