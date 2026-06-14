"""Shared helpers for analytics aggregation."""
from __future__ import annotations

from typing import Iterable

from psycopg2.extensions import connection as PGConnection

from football.config import COMPETITION_ID, SEASON_ID


def resolve_match_ids(
    conn: PGConnection,
    competition_id: int,
    season_id: int,
    match_ids: Iterable[int] | None,
) -> list[int]:
    with conn.cursor() as cur:
        if match_ids is None:
            cur.execute(
                """
                SELECT match_id FROM staging.matches
                WHERE competition_id = %s AND season_id = %s
                ORDER BY match_id
                """,
                (competition_id, season_id),
            )
        else:
            ids = [int(mid) for mid in match_ids]
            cur.execute(
                """
                SELECT match_id FROM staging.matches
                WHERE competition_id = %s AND season_id = %s AND match_id = ANY(%s)
                ORDER BY match_id
                """,
                (competition_id, season_id, ids),
            )
            found = {row[0] for row in cur.fetchall()}
            missing = sorted(set(ids) - found)
            if missing:
                raise ValueError(f"match_ids not found for competition/season: {missing}")
            return ids
        return [row[0] for row in cur.fetchall()]


def delete_fact_for_matches(conn: PGConnection, match_ids: list[int]) -> None:
    if not match_ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM analytics.fact_player_match_stats WHERE match_id = ANY(%s)",
            (match_ids,),
        )


def delete_formation_for_matches(conn: PGConnection, match_ids: list[int]) -> None:
    if not match_ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM analytics.team_match_formation WHERE match_id = ANY(%s)",
            (match_ids,),
        )


def delete_analytics_for_matches(conn: PGConnection, match_ids: list[int]) -> None:
    delete_fact_for_matches(conn, match_ids)
    delete_formation_for_matches(conn, match_ids)


def delete_analytics_for_season(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    match_ids: Iterable[int] | None = None,
) -> list[int]:
    ids = resolve_match_ids(conn, competition_id, season_id, match_ids)
    delete_analytics_for_matches(conn, ids)
    return ids
