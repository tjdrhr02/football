"""Aggregate staging.events + lineups → analytics.fact_player_match_stats."""
from __future__ import annotations

from typing import Iterable

from psycopg2.extensions import connection as PGConnection

from football.aggregation.common import delete_fact_for_matches, resolve_match_ids
from football.config import COMPETITION_ID, SEASON_ID
from football.sql_loader import load_sql

FACT_INSERT_SQL = load_sql("aggregate", "fact_player_match_stats.sql")


def aggregate_fact_player_match_stats(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    match_ids: Iterable[int] | None = None,
    replace: bool = True,
) -> int:
    """Build player-match facts for scoped matches. Returns rows inserted."""
    ids = resolve_match_ids(conn, competition_id, season_id, match_ids)
    if replace:
        delete_fact_for_matches(conn, ids)

    with conn.cursor() as cur:
        cur.execute(FACT_INSERT_SQL, {"match_ids": ids})
        inserted = cur.rowcount
    return inserted
