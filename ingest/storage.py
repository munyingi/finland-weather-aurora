"""Raw layer in DuckDB. Every table has a natural primary key and loads use
INSERT OR REPLACE, so re-running any window is idempotent: the latest value wins."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from . import config

DDL = """
create schema if not exists raw;

create table if not exists raw.fmi_observations (
    position_key  varchar   not null,
    station_lat   double    not null,
    station_lon   double    not null,
    observed_at   timestamp not null,
    parameter     varchar   not null,
    value         double    not null,
    loaded_at     timestamp not null,
    run_id        varchar   not null,
    primary key (position_key, observed_at, parameter)
);

create table if not exists raw.fmi_stations (
    fmisid        integer   primary key,
    station_name  varchar,
    municipality  varchar,
    lat           double    not null,
    lon           double    not null,
    position_key  varchar   not null,
    networks      varchar,
    active_from   timestamp,
    active_to     timestamp,
    loaded_at     timestamp not null,
    run_id        varchar   not null
);

create table if not exists raw.swpc_kp (
    block_start   timestamp not null,
    product       varchar   not null,
    kp            double    not null,
    status        varchar   not null,
    noaa_scale    varchar,
    loaded_at     timestamp not null,
    run_id        varchar   not null,
    primary key (block_start, product)
);

create table if not exists raw.swpc_solar_wind (
    observed_at   timestamp primary key,
    bz_gsm_nt     double,
    bt_nt         double,
    speed_kms     double,
    density_cm3   double,
    loaded_at     timestamp not null,
    run_id        varchar   not null
);

create table if not exists raw.openmeteo_cloud (
    cell_id              varchar   not null,
    valid_at             timestamp not null,
    cloud_cover_pct      double    not null,
    cloud_cover_low_pct  double,
    loaded_at            timestamp not null,
    run_id               varchar   not null,
    primary key (cell_id, valid_at)
);

create table if not exists raw.grid_cells (
    cell_id         varchar primary key,
    h3_res          integer not null,
    parent_cell_id  varchar,
    lat             double  not null,
    lon             double  not null,
    region_code     varchar not null,
    region_name     varchar not null,
    region_name_fi  varchar,
    loaded_at       timestamp not null,
    run_id          varchar not null
);

create table if not exists raw.ingest_runs (
    run_id       varchar   not null,
    source       varchar   not null,
    mode         varchar   not null,
    started_at   timestamp not null,
    finished_at  timestamp,
    status       varchar   not null,
    row_count    integer,
    window_start timestamp,
    window_end   timestamp,
    error        varchar,
    primary key (run_id, source)
);
"""


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def connect(path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    path = Path(path or config.WAREHOUSE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute(DDL)
    return con


def upsert(con: duckdb.DuckDBPyConnection, table: str, rows: list[dict], run_id: str) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    df["loaded_at"] = utcnow()
    df["run_id"] = run_id
    cols = [r[0] for r in con.execute(f"describe raw.{table}").fetchall()]
    df = df.reindex(columns=cols)
    con.register("_incoming", df)
    try:
        con.execute(f"insert or replace into raw.{table} select * from _incoming")
    finally:
        con.unregister("_incoming")
    return len(df)


def new_run_id() -> str:
    return f"{utcnow():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


@contextmanager
def tracked(con, run_id: str, source: str, mode: str, window: tuple[datetime, datetime] | None = None):
    """Audit every source load in raw.ingest_runs, including failures."""
    started = utcnow()
    state = {"rows": 0}
    con.execute(
        "insert or replace into raw.ingest_runs values (?, ?, ?, ?, null, 'running', null, ?, ?, null)",
        [run_id, source, mode, started, *(window or (None, None))],
    )
    try:
        yield state
    except Exception as exc:
        con.execute(
            "update raw.ingest_runs set finished_at = ?, status = 'failed', error = ? where run_id = ? and source = ?",
            [utcnow(), str(exc)[:2000], run_id, source],
        )
        raise
    con.execute(
        "update raw.ingest_runs set finished_at = ?, status = 'success', row_count = ? where run_id = ? and source = ?",
        [utcnow(), state["rows"], run_id, source],
    )


def fmi_watermark(con) -> datetime | None:
    return con.execute("select max(observed_at) from raw.fmi_observations").fetchone()[0]


def grid_cells(con, h3_res: int) -> list[dict]:
    cur = con.execute("select cell_id, lat, lon from raw.grid_cells where h3_res = ? order by cell_id", [h3_res])
    return [dict(zip(("cell_id", "lat", "lon"), r, strict=True)) for r in cur.fetchall()]
