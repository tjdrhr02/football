"""Run staging → analytics aggregation (SQL ETL)."""
from __future__ import annotations

import argparse
import sys

from football.config import COMPETITION_ID, DEFAULT_DB, SEASON_ID
from football.db.connection import transaction
from football.pipeline.aggregate import TABLE_STEPS, run_analytics_aggregate
from football.pipeline.reporting import print_analytics_counts, print_compression_summary


def print_formation_sample(conn, match_id: int = 3869253) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT team_id, from_minute, to_minute, formation_code, source_event_type
            FROM analytics.team_match_formation
            WHERE match_id = %s
            ORDER BY team_id, from_minute
            """,
            (match_id,),
        )
        rows = cur.fetchall()
        if rows:
            print(f"\n--- formation timeline (match {match_id}) ---")
            for row in rows:
                print(f"  team={row[0]} {row[1]}'→{row[2]} {row[3]} ({row[4]})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate staging into analytics")
    parser.add_argument(
        "--table",
        choices=TABLE_STEPS,
        default="all",
        help="Aggregate formation timeline, player facts, or both",
    )
    parser.add_argument("--competition-id", type=int, default=COMPETITION_ID)
    parser.add_argument("--season-id", type=int, default=SEASON_ID)
    parser.add_argument("--dbname", default=DEFAULT_DB)
    parser.add_argument(
        "--match-id",
        type=int,
        action="append",
        dest="match_ids",
        help="Limit aggregation to specific match(es)",
    )
    parser.add_argument(
        "--counts-only",
        action="store_true",
        help="Print analytics counts and exit",
    )
    parser.add_argument(
        "--sample-formation-match-id",
        type=int,
        default=3869253,
        help="Print formation timeline sample after run",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Use checkmark completion lines for ETL steps",
    )
    args = parser.parse_args(argv)

    try:
        if args.counts_only:
            with transaction(args.dbname) as conn:
                print_analytics_counts(conn, args.competition_id, args.season_id)
                print_compression_summary(conn, args.competition_id, args.season_id)
                print_formation_sample(conn, args.sample_formation_match_id)
            return 0

        with transaction(args.dbname) as conn:
            run_analytics_aggregate(
                conn,
                args.table,
                args.competition_id,
                args.season_id,
                args.match_ids,
                verbose=args.verbose,
            )
            print_analytics_counts(conn, args.competition_id, args.season_id)
            print_compression_summary(conn, args.competition_id, args.season_id)
            print_formation_sample(conn, args.sample_formation_match_id)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
