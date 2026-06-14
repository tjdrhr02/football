"""Full StatsBomb pipeline: staging ingest → analytics aggregate."""
from __future__ import annotations

import argparse
import sys

from psycopg2.extensions import connection as PGConnection

from football.config import COMPETITION_ID, DEFAULT_DB, SEASON_ID
from football.db.connection import transaction
from football.pipeline.aggregate import run_analytics_aggregate
from football.pipeline.ingest import run_staging_ingest
from football.pipeline.reporting import (
    print_analytics_counts,
    print_compression_summary,
    print_staging_counts,
)
from football.pipeline.tracking import finish_ingestion_run, start_ingestion_run


def run_full_pipeline(
    conn: PGConnection,
    competition_id: int,
    season_id: int,
    match_ids: list[int] | None = None,
    *,
    skip_staging: bool = False,
    skip_analytics: bool = False,
    verbose: bool = True,
) -> tuple[int, int, int, int]:
    """
    Run staging ingest then analytics aggregation for a competition/season.

    Returns (matches_processed, events_processed, formation_rows, fact_rows).
    """
    matches_processed = 0
    events_processed = 0
    formation_rows = 0
    fact_rows = 0

    if not skip_staging:
        if verbose:
            print(f"\n=== staging ingest (competition_id={competition_id}, season_id={season_id}) ===")
        matches_processed, events_processed = run_staging_ingest(
            conn,
            "all",
            competition_id,
            season_id,
            match_ids=match_ids,
            verbose=verbose,
        )

    if not skip_analytics:
        if verbose:
            print(f"\n=== analytics aggregate (competition_id={competition_id}, season_id={season_id}) ===")
        formation_rows, fact_rows = run_analytics_aggregate(
            conn,
            "all",
            competition_id,
            season_id,
            match_ids=match_ids,
            verbose=verbose,
        )

    return matches_processed, events_processed, formation_rows, fact_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="StatsBomb Open Data → staging → analytics (full pipeline)",
    )
    parser.add_argument("--competition-id", type=int, default=COMPETITION_ID)
    parser.add_argument("--season-id", type=int, default=SEASON_ID)
    parser.add_argument("--dbname", default=DEFAULT_DB)
    parser.add_argument(
        "--match-id",
        type=int,
        action="append",
        dest="match_ids",
        help="Limit to specific match(es)",
    )
    parser.add_argument(
        "--skip-staging",
        action="store_true",
        help="Run analytics only (staging must already be loaded)",
    )
    parser.add_argument(
        "--skip-analytics",
        action="store_true",
        help="Run staging ingest only",
    )
    parser.add_argument(
        "--no-run-log",
        action="store_true",
        help="Skip staging.ingestion_runs bookkeeping",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output (no per-match progress lines)",
    )
    parser.add_argument(
        "--counts-only",
        action="store_true",
        help="Print staging/analytics counts and compression summary, then exit",
    )
    args = parser.parse_args(argv)

    if args.skip_staging and args.skip_analytics:
        print("[error] cannot skip both staging and analytics", file=sys.stderr)
        return 1

    try:
        if args.counts_only:
            with transaction(args.dbname) as conn:
                print_staging_counts(conn, args.competition_id, args.season_id)
                print_analytics_counts(conn, args.competition_id, args.season_id)
                print_compression_summary(conn, args.competition_id, args.season_id)
            return 0

        run_id = None
        if not args.no_run_log and not args.skip_staging:
            with transaction(args.dbname) as conn:
                run_id = start_ingestion_run(conn, args.competition_id, args.season_id)

        try:
            with transaction(args.dbname) as conn:
                matches_processed, events_processed, _, _ = run_full_pipeline(
                    conn,
                    args.competition_id,
                    args.season_id,
                    match_ids=args.match_ids,
                    skip_staging=args.skip_staging,
                    skip_analytics=args.skip_analytics,
                    verbose=not args.quiet,
                )
                if not args.quiet:
                    print_staging_counts(conn, args.competition_id, args.season_id)
                    if not args.skip_analytics:
                        print_analytics_counts(conn, args.competition_id, args.season_id)
                        print_compression_summary(conn, args.competition_id, args.season_id)
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
