"""Command-line interface for transit-analytics."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from . import analytics, dashboard, gtfs, ridership, sample_feed


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def cmd_build_sample(args: argparse.Namespace) -> int:
    out = sample_feed.build_feed(args.out, zip_path=args.zip)
    print(f"Sample GTFS feed written to {out}" + (f" and {args.zip}" if args.zip else ""))
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    conn = gtfs.connect(args.db)
    counts = gtfs.load_feed(args.feed, conn)
    for table, count in counts.items():
        print(f"  {table:<16} {count:>8,} rows")
    print(f"Feed loaded into {args.db}")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    conn = gtfs.connect(args.db)
    start, days = args.start, args.days
    if start is None or days is None:
        auto_start, auto_days = gtfs.pick_simulation_window(conn)
        start = start or auto_start
        days = days or auto_days
        print(f"Auto-detected simulation window from feed calendar: "
              f"{days} days starting {start}")
    written = ridership.simulate(conn, start=start, days=days, seed=args.seed)
    print(f"Simulated {written:,} stop-level APC records "
          f"({days} days from {start}, seed={args.seed})")
    return 0


def cmd_load_apc(args: argparse.Namespace) -> int:
    conn = gtfs.connect(args.db)
    written = ridership.load_apc_csv(conn, args.csv)
    print(f"Loaded {written:,} APC records from {args.csv}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    conn = gtfs.connect(args.db)
    summary = analytics.system_summary(conn)
    if not summary["days"]:
        print("No ridership data loaded. Run `simulate` or `load-apc` first.")
        return 1

    print("=== System summary ===")
    print(f"  Service days analyzed : {summary['days']}")
    print(f"  Total boardings       : {summary['total_boardings']:,}")
    print(f"  Avg weekday boardings : {summary['avg_weekday_boardings']:,}")
    print(f"  Avg weekend boardings : {summary['avg_weekend_boardings']:,}")
    if summary["busiest_route"]:
        r = summary["busiest_route"]
        print(f"  Busiest route         : {r['short_name']} "
              f"({r['avg_daily_boardings']:,} boardings/day)")
    if summary["busiest_stop"]:
        s = summary["busiest_stop"]
        print(f"  Busiest stop          : {s['stop_name']} "
              f"({s['avg_daily_boardings']:,} boardings/day)")

    print("\n=== Routes by average daily boardings ===")
    print(f"  {'Route':<10} {'Brd/day':>9} {'Trips/day':>10} "
          f"{'Brd/trip':>9} {'Brd/rev-hr':>11}")
    for r in analytics.boardings_by_route(conn):
        per_hour = r["boardings_per_revenue_hour"]
        print(f"  {r['short_name']:<10} {r['avg_daily_boardings']:>9,} "
              f"{r['trips_per_day']:>10} {r['boardings_per_trip']:>9} "
              f"{per_hour if per_hour is not None else '—':>11}")

    print("\n=== Top 10 stops ===")
    for s in analytics.top_stops(conn, limit=10):
        print(f"  {s['stop_name']:<36} {s['avg_daily_boardings']:>7,} boardings/day")

    print("\n=== Scheduled weekday headways ===")
    for h in analytics.route_headways(conn):
        print(f"  {h['short_name']:<10} {h['trips_per_weekday']:>4} trips  "
              f"min {h['min_headway_min']:>3} min / median "
              f"{h['median_headway_min']:>3} min  span {h['span']}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    conn = gtfs.connect(args.db)
    if not analytics.system_summary(conn)["days"]:
        print("No ridership data loaded. Run `simulate` or `load-apc` first.")
        return 1
    out = dashboard.write(conn, args.out, title=args.title)
    print(f"Dashboard written to {out}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Full pipeline: sample feed -> ingest -> simulate -> report + dashboard."""
    demo_dir = Path(args.dir)
    feed_dir = demo_dir / "gtfs_sample"
    db_path = demo_dir / "transit.db"

    print("[1/4] Building sample GTFS feed (modeled on Sound Transit)…")
    sample_feed.build_feed(feed_dir, zip_path=demo_dir / "gtfs_sample.zip")

    print("[2/4] Ingesting feed into SQLite…")
    conn = gtfs.connect(db_path)
    for table, count in gtfs.load_feed(feed_dir, conn).items():
        print(f"  {table:<16} {count:>8,} rows")

    print(f"[3/4] Simulating {args.days} days of APC ridership "
          f"from {args.start} (seed={args.seed})…")
    written = ridership.simulate(conn, start=args.start, days=args.days, seed=args.seed)
    print(f"  {written:,} stop-level records")

    print("[4/4] Writing report and dashboard…")
    report_args = argparse.Namespace(db=db_path)
    cmd_report(report_args)
    out = dashboard.write(conn, demo_dir / "dashboard.html")
    print(f"\nDashboard: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transit-analytics",
        description="Transit ridership analytics on GTFS data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build-sample", help="generate the sample GTFS feed")
    p.add_argument("--out", default="data/gtfs_sample", help="output directory")
    p.add_argument("--zip", default=None, help="also write a .zip archive here")
    p.set_defaults(func=cmd_build_sample)

    p = sub.add_parser("ingest", help="load a GTFS feed (zip or directory) into SQLite")
    p.add_argument("feed", help="path to GTFS .zip or directory")
    p.add_argument("--db", default="transit.db")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("simulate", help="generate simulated APC ridership")
    p.add_argument("--db", default="transit.db")
    p.add_argument("--start", type=_parse_date, default=None,
                   help="first service date (YYYY-MM-DD); default: "
                        "auto-detected from the feed's calendar")
    p.add_argument("--days", type=int, default=None,
                   help="default: up to 28, bounded by the feed's calendar window")
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("load-apc", help="load real APC ridership from CSV")
    p.add_argument("csv", help="CSV with service_date,trip_id,stop_id,"
                               "stop_sequence,boardings,alightings[,load]")
    p.add_argument("--db", default="transit.db")
    p.set_defaults(func=cmd_load_apc)

    p = sub.add_parser("report", help="print analytics summary to the terminal")
    p.add_argument("--db", default="transit.db")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("dashboard", help="write the HTML dashboard")
    p.add_argument("--db", default="transit.db")
    p.add_argument("--out", default="dashboard.html")
    p.add_argument("--title", default="Transit Ridership Analytics")
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("demo", help="run the full pipeline end-to-end in ./demo")
    p.add_argument("--dir", default="demo")
    p.add_argument("--start", type=_parse_date, default=date(2026, 3, 2))
    p.add_argument("--days", type=int, default=28)
    p.add_argument("--seed", type=int, default=42)
    p.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except gtfs.GTFSValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
