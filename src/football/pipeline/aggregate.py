"""Analytics aggregation orchestration (staging → analytics)."""
from __future__ import annotations

from typing import Literal

from psycopg2.extensions import connection as PGConnection

from football.aggregation.fact_player_match_stats import aggregate_fact_player_match_stats
from football.aggregation.team_match_formation import aggregate_team_match_formation

TABLE_STEPS = ("formation", "fact", "all")


def run_analytics_aggregate(
    conn: PGConnection,
    table: Literal["formation", "fact", "all"],
    competition_id: int,
    season_id: int,
    match_ids: list[int] | None = None,
    *,
    verbose: bool = False,
) -> tuple[int, int]:
    """Run formation and/or fact aggregation. Returns (formation_rows, fact_rows)."""
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
        if verbose:
            print(f"✓ team_match_formation ETL 완료: {formation_rows:,}행")
        else:
            print(f"[ok] team_match_formation: {formation_rows:,} row(s)")

    if table in ("fact", "all"):
        fact_rows = aggregate_fact_player_match_stats(
            conn,
            competition_id,
            season_id,
            match_ids=match_ids,
            replace=True,
        )
        if verbose:
            print(f"✓ fact_player_match_stats ETL 완료: {fact_rows:,}행")
        else:
            print(f"[ok] fact_player_match_stats: {fact_rows:,} row(s)")

    return formation_rows, fact_rows
