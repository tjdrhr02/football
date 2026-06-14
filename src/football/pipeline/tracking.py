"""staging.ingestion_runs bookkeeping."""
from __future__ import annotations

from psycopg2.extensions import connection as PGConnection


def start_ingestion_run(conn: PGConnection, competition_id: int, season_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO staging.ingestion_runs (
                source, competition_id, season_id, started_at, status
            ) VALUES ('statsbomb_open', %s, %s, now(), 'running')
            RETURNING run_id
            """,
            (competition_id, season_id),
        )
        return cur.fetchone()[0]


def finish_ingestion_run(
    conn: PGConnection,
    run_id: int,
    status: str,
    matches_processed: int = 0,
    events_processed: int = 0,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE staging.ingestion_runs
            SET finished_at = now(),
                status = %s,
                matches_processed = %s,
                events_processed = %s,
                error_message = %s
            WHERE run_id = %s
            """,
            (status, matches_processed, events_processed, error_message, run_id),
        )
