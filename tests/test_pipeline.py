from datetime import datetime, timedelta

from ingest import config, pipeline
from ingest.demo import DemoClient


def _counts(con):
    tables = ["fmi_observations", "fmi_stations", "swpc_kp", "swpc_solar_wind", "openmeteo_cloud", "grid_cells"]
    return {t: con.execute(f"select count(*) from raw.{t}").fetchone()[0] for t in tables}


def test_rerunning_the_same_window_is_idempotent(con, now):
    first = pipeline.run(DemoClient(now), mode="demo", now=now, backfill_hours=12, con=con)
    assert not first["failed"]
    before = _counts(con)
    second = pipeline.run(DemoClient(now), mode="demo", now=now, backfill_hours=12, con=con)
    assert not second["failed"]
    assert _counts(con) == before
    assert second["sources"]["grid"] == 0  # grid is built once
    assert second["sources"]["fmi_stations"] == 0  # stations refresh daily


def test_incremental_run_only_reads_from_watermark_minus_overlap(con, now):
    pipeline.run(DemoClient(now), mode="demo", now=now, backfill_hours=12, con=con)
    later = now + timedelta(hours=3)
    client = DemoClient(later)
    pipeline.run(client, mode="demo", now=later, backfill_hours=12, con=con)
    runs = con.execute(
        "select window_start, window_end from raw.ingest_runs where source = 'fmi_observations' order by started_at"
    ).fetchall()
    last_start, last_end = runs[-1]
    assert last_start == datetime(2026, 11, 17, 18) - timedelta(hours=config.FMI_OVERLAP_HOURS)
    assert last_end == datetime(2026, 11, 17, 22)
    latest = con.execute("select max(observed_at) from raw.fmi_observations").fetchone()[0]
    assert latest == datetime(2026, 11, 17, 21)


def test_failing_source_is_recorded_and_others_still_load(con, now):
    class Flaky(DemoClient):
        def get(self, url, params=None):
            if "swpc" in url:
                raise ConnectionError("SWPC unreachable")
            return super().get(url, params)

    summary = pipeline.run(Flaky(now), mode="demo", now=now, backfill_hours=6, con=con)
    assert {f["source"] for f in summary["failed"]} == {"swpc_kp", "swpc_solar_wind"}
    assert summary["sources"]["fmi_observations"] > 0
    status = dict(con.execute("select source, status from raw.ingest_runs").fetchall())
    assert status["swpc_kp"] == "failed" and status["openmeteo_cloud"] == "success"


def test_fmi_window_rules(now):
    # empty warehouse -> full backfill
    assert pipeline.fmi_window(None, now, 72) == (datetime(2026, 11, 14, 19), datetime(2026, 11, 17, 19))
    # stale watermark older than the backfill horizon is clipped to the horizon
    assert pipeline.fmi_window(now - timedelta(days=30), now, 72)[0] == datetime(2026, 11, 14, 19)
    # backfill never exceeds FMI's 7-day limit
    assert pipeline.fmi_window(None, now, 1000)[0] == datetime(2026, 11, 10, 19)
