"""CLI: python -m ingest {run,demo,publish}"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from . import config, pipeline, publish, storage
from .demo import DemoClient
from .http import HttpClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingest", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Ingest live data from FMI, NOAA SWPC and Open-Meteo")
    run_p.add_argument("--sources", default=",".join(pipeline.ALL_SOURCES))
    run_p.add_argument("--backfill-hours", type=int, default=config.DEFAULT_BACKFILL_HOURS)
    run_p.add_argument("--rebuild-grid", action="store_true")
    run_p.add_argument("--strict", action="store_true", help="Exit non-zero if any source fails")

    demo_p = sub.add_parser("demo", help="Load synthetic data in the real API formats (no network)")
    demo_p.add_argument("--backfill-hours", type=int, default=72)
    demo_p.add_argument("--now", help="Pretend current UTC time, ISO format")

    pub_p = sub.add_parser("publish", help="Export dashboard Parquet files")
    pub_p.add_argument("--out", default=str(config.PUBLISH_DIR))
    pub_p.add_argument("--mode", default="live")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "publish":
        print(json.dumps(publish.publish(args.out, mode=args.mode), indent=2))
        return 0

    if args.cmd == "demo":
        now = datetime.fromisoformat(args.now) if args.now else storage.utcnow()
        summary = pipeline.run(DemoClient(now), mode="demo", now=now, backfill_hours=args.backfill_hours)
    else:
        sources = tuple(s.strip() for s in args.sources.split(",") if s.strip())
        summary = pipeline.run(HttpClient(), sources=sources, backfill_hours=args.backfill_hours, rebuild_grid=args.rebuild_grid)

    print(json.dumps(summary, indent=2, default=str))
    nothing_loaded = not summary["sources"]
    if summary["failed"] and (getattr(args, "strict", False) or nothing_loaded):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
