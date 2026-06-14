"""Load StatsBomb data into staging tables (table-by-table)."""
from __future__ import annotations

import argparse
import sys
import warnings

warnings.filterwarnings("ignore")

from football.config import COMPETITION_ID, DEFAULT_DB, SEASON_ID
from football.db.connection import transaction
from football.pipeline.ingest import TABLE_STEPS, run_staging_ingest
from football.pipeline.reporting import print_staging_counts
from football.pipeline.tracking import finish_ingestion_run, start_ingestion_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest StatsBomb Open Data into staging")
    parser.add_argument(
        "--table",
        choices=TABLE_STEPS,
        default="all",
        help="Load a single staging table (or all in FK order)",
    )
    parser.add_argument("--competition-id", type=int, default=COMPETITION_ID)
    parser.add_argument("--season-id", type=int, default=SEASON_ID)
    parser.add_argument("--dbname", default=DEFAULT_DB)
    parser.add_argument(
        "--match-id",
        type=int,
        action="append",
        dest="match_ids",
        help="Limit events/lineups/players to specific match(es)",
    )
    parser.add_argument(
        "--no-run-log",
        action="store_true",
        help="Skip staging.ingestion_runs bookkeeping",
    )
    parser.add_argument(
        "--counts-only",
        action="store_true",
        help="Print staging row counts and exit",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Per-match progress for events load",
    )
    args = parser.parse_args(argv)

    if args.counts_only:
        try:
            with transaction(args.dbname) as conn:
                print_staging_counts(conn, args.competition_id, args.season_id)
            return 0
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1

    try:
        run_id = None
        if not args.no_run_log:
            with transaction(args.dbname) as conn:
                run_id = start_ingestion_run(conn, args.competition_id, args.season_id)

        try:
            with transaction(args.dbname) as conn:
                matches_processed, events_processed = run_staging_ingest(
                    conn,
                    args.table,
                    args.competition_id,
                    args.season_id,
                    args.match_ids,
                    verbose=args.verbose,
                )
                print_staging_counts(conn, args.competition_id, args.season_id)
        except Exception as exc:
            if run_id is not None:
                with transaction(args.dbname) as conn:
                    finish_ingestion_run(conn, run_id, "failed", error_message=str(exc))
            raise

        if run_id is not None:
            with transaction(args.dbname) as conn:
                finish_ingestion_run(
                    conn,
                    run_id,
                    "success",
                    matches_processed=matches_processed,
                    events_processed=events_processed,
                )

    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
