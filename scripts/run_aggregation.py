"""Run staging → analytics aggregation (SQL ETL)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import bootstrap

bootstrap()

from football.aggregation.fact_player_match_stats import aggregate_fact_player_match_stats
from football.aggregation.team_match_formation import aggregate_team_match_formation
from football.config import COMPETITION_ID, DEFAULT_DB, KOREA_TEAM_ID, SEASON_ID
from football.db.connection import transaction

TABLE_STEPS = ("formation", "fact", "all")


def print_counts(conn, competition_id: int, season_id: int) -> None:
    with conn.cursor() as cur:
        print("\n--- analytics counts ---")
        cur.execute("SELECT COUNT(*) FROM analytics.fact_player_match_stats")
        print(f"  fact_player_match_stats   {cur.fetchone()[0]:,}")

        cur.execute("SELECT COUNT(*) FROM analytics.team_match_formation")
        print(f"  team_match_formation      {cur.fetchone()[0]:,}")

        cur.execute(
            """
            SELECT COUNT(*) FROM analytics.fact_player_match_stats f
            INNER JOIN staging.matches m ON m.match_id = f.match_id
            WHERE m.competition_id = %s AND m.season_id = %s
            """,
            (competition_id, season_id),
        )
        print(f"  fact (season scope)       {cur.fetchone()[0]:,}")

        cur.execute(
            """
            SELECT COUNT(*) FROM analytics.fact_player_match_stats
            WHERE team_id = %s
            """,
            (KOREA_TEAM_ID,),
        )
        print(f"  fact (Korea {KOREA_TEAM_ID})     {cur.fetchone()[0]:,}")


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


def run_table(
    conn,
    table: str,
    competition_id: int,
    season_id: int,
    match_ids: list[int] | None,
) -> tuple[int, int]:
    formation_rows = 0
    fact_rows = 0

    if table in ("formation", "all"):
        formation_rows = aggregate_team_match_formation(
            conn,
            competition_id,
            season_id,
            match_ids=match_ids,
            replace=True,
        )
        print(f"[ok] team_match_formation: {formation_rows:,} row(s)")

    if table in ("fact", "all"):
        fact_rows = aggregate_fact_player_match_stats(
            conn,
            competition_id,
            season_id,
            match_ids=match_ids,
            replace=True,
        )
        print(f"[ok] fact_player_match_stats: {fact_rows:,} row(s)")

    return formation_rows, fact_rows


def main() -> int:
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
    args = parser.parse_args()

    try:
        if args.counts_only:
            with transaction(args.dbname) as conn:
                print_counts(conn, args.competition_id, args.season_id)
                print_formation_sample(conn, args.sample_formation_match_id)
            return 0

        with transaction(args.dbname) as conn:
            run_table(
                conn,
                args.table,
                args.competition_id,
                args.season_id,
                args.match_ids,
            )
            print_counts(conn, args.competition_id, args.season_id)
            print_formation_sample(conn, args.sample_formation_match_id)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
