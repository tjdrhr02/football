"""Aggregate staging.events + lineups → analytics.team_match_formation."""
from __future__ import annotations

from typing import Iterable

from psycopg2.extensions import connection as PGConnection

from football.aggregation.common import delete_formation_for_matches, resolve_match_ids
from football.config import COMPETITION_ID, SEASON_ID

FORMATION_INSERT_SQL = """
WITH scoped_matches AS (
    SELECT unnest(%(match_ids)s::int[]) AS match_id
),
formation_events AS (
    SELECT
        e.match_id,
        e.team_id,
        e.type AS source_event_type,
        COALESCE(e.minute, 0)::smallint AS from_minute,
        e.index,
        e.payload->'tactics'->>'formation' AS formation_code
    FROM staging.events e
    INNER JOIN scoped_matches sm ON sm.match_id = e.match_id
    WHERE e.type IN ('Starting XI', 'Tactical Shift')
      AND e.team_id IS NOT NULL
      AND e.payload->'tactics'->>'formation' IS NOT NULL
),
formation_changes AS (
    SELECT
        fe.*,
        LAG(fe.formation_code) OVER (
            PARTITION BY fe.match_id, fe.team_id
            ORDER BY fe.index
        ) AS prev_formation_code
    FROM formation_events fe
),
deduped_changes AS (
    SELECT DISTINCT ON (fc.match_id, fc.team_id, fc.from_minute)
        fc.match_id,
        fc.team_id,
        fc.source_event_type,
        fc.from_minute,
        fc.index,
        fc.formation_code
    FROM formation_changes fc
    WHERE fc.prev_formation_code IS DISTINCT FROM fc.formation_code
    ORDER BY fc.match_id, fc.team_id, fc.from_minute, fc.index DESC
),
timeline AS (
    SELECT
        dc.match_id,
        dc.team_id,
        dc.from_minute,
        LEAD(dc.from_minute) OVER (
            PARTITION BY dc.match_id, dc.team_id
            ORDER BY dc.index
        ) AS to_minute,
        dc.formation_code,
        dc.source_event_type
    FROM deduped_changes dc
)
INSERT INTO analytics.team_match_formation (
    match_id,
    team_id,
    from_minute,
    to_minute,
    formation_code,
    source_event_type
)
SELECT
    match_id,
    team_id,
    from_minute,
    to_minute,
    formation_code,
    source_event_type
FROM timeline
"""


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
