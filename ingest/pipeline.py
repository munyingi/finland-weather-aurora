"""Ingestion orchestration: grid -> FMI -> SWPC -> Open-Meteo, each source tracked separately.

A failing source is recorded in raw.ingest_runs and does not stop the others,
so one flaky API never blanks the whole dashboard.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from . import config, fmi, grid, openmeteo, storage, swpc
from .http import Client

log = logging.getLogger(__name__)

ALL_SOURCES = ("grid", "fmi", "swpc", "openmeteo")


def floor_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def fmi_window(watermark: datetime | None, now: datetime, backfill_hours: int) -> tuple[datetime, datetime]:
    """Incremental window with overlap; falls back to a backfill when the warehouse is empty or stale."""
    end = floor_hour(now) + timedelta(hours=1)  # exclusive, includes the current hour
    floor = end - timedelta(hours=min(backfill_hours, config.FMI_MAX_SPAN_HOURS))
    if watermark is None:
        return floor, end
    start = floor_hour(watermark) - timedelta(hours=config.FMI_OVERLAP_HOURS)
    return max(start, floor), end


def run(
    client: Client,
    *,
    mode: str = "live",
    sources: tuple[str, ...] = ALL_SOURCES,
    now: datetime | None = None,
    backfill_hours: int = config.DEFAULT_BACKFILL_HOURS,
    rebuild_grid: bool = False,
    con=None,
) -> dict:
    con = con or storage.connect()
    now = now or storage.utcnow()
    run_id = storage.new_run_id()
    summary: dict = {"run_id": run_id, "mode": mode, "sources": {}, "failed": []}

    def step(source: str, fn, window=None):
        try:
            with storage.tracked(con, run_id, source, mode, window) as state:
                state["rows"] = fn()
            summary["sources"][source] = state["rows"]
            log.info("%s: %s rows", source, state["rows"])
        except Exception as exc:  # recorded in raw.ingest_runs by tracked()
            log.exception("%s failed", source)
            summary["failed"].append({"source": source, "error": str(exc)})

    if "grid" in sources:

        def load_grid() -> int:
            have = con.execute("select count(*) from raw.grid_cells").fetchone()[0]
            if have and not rebuild_grid:
                return 0
            weather, aurora = grid.build_cells()
            con.execute("delete from raw.grid_cells")
            return storage.upsert(con, "grid_cells", weather + aurora, run_id)

        step("grid", load_grid)

    if "fmi" in sources:

        def load_stations() -> int:
            last = con.execute("select max(loaded_at) from raw.fmi_stations").fetchone()[0]
            if last and now - last < timedelta(hours=24):
                return 0  # station metadata changes rarely; refresh daily
            return storage.upsert(con, "fmi_stations", fmi.fetch_stations(client), run_id)

        step("fmi_stations", load_stations)
        window = fmi_window(storage.fmi_watermark(con), now, backfill_hours)
        step(
            "fmi_observations",
            lambda: storage.upsert(con, "fmi_observations", fmi.fetch_observations(client, *window), run_id),
            window,
        )

    if "swpc" in sources:
        step("swpc_kp", lambda: storage.upsert(con, "swpc_kp", swpc.fetch_kp(client), run_id))
        step("swpc_solar_wind", lambda: storage.upsert(con, "swpc_solar_wind", swpc.fetch_solar_wind(client), run_id))

    if "openmeteo" in sources:

        def load_cloud() -> int:
            cells = storage.grid_cells(con, config.H3_RES_AURORA)
            if not cells:
                raise RuntimeError("No aurora grid cells; run the grid source first")
            return storage.upsert(con, "openmeteo_cloud", openmeteo.fetch_cloud(client, cells), run_id)

        step("openmeteo_cloud", load_cloud)

    return summary
