"""Aggregate staging.events + lineups → analytics.team_match_formation."""
from __future__ import annotations

from typing import Iterable

from psycopg2.extensions import connection as PGConnection

from football.aggregation.common import delete_formation_for_matches, resolve_match_ids
from football.config import COMPETITION_ID, SEASON_ID
from football.sql_loader import load_sql

FORMATION_INSERT_SQL = load_sql("aggregate", "team_match_formation.sql")


def aggregate_team_match_formation(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    match_ids: Iterable[int] | None = None,
    replace: bool = True,
) -> int:
    """Build formation timelines for scoped matches. Returns rows inserted."""
    ids = resolve_match_ids(conn, competition_id, season_id, match_ids)
    if replace:
        delete_formation_for_matches(conn, ids)

    with conn.cursor() as cur:
        cur.execute(FORMATION_INSERT_SQL, {"match_ids": ids})
        inserted = cur.rowcount
    return inserted
