"""Pipeline progress output and row-count summaries."""
from __future__ import annotations

from psycopg2.extensions import connection as PGConnection

from football.config import KOREA_TEAM_ID


def print_staging_counts(conn: PGConnection, competition_id: int, season_id: int) -> None:
    queries = {
        "competitions": "SELECT COUNT(*) FROM staging.competitions",
        "seasons": "SELECT COUNT(*) FROM staging.seasons",
        "teams": "SELECT COUNT(*) FROM staging.teams",
        "players": "SELECT COUNT(*) FROM staging.players",
        "matches": (
            "SELECT COUNT(*) FROM staging.matches "
            "WHERE competition_id = %s AND season_id = %s"
        ),
        "events (season)": (
            """
            SELECT COUNT(*) FROM staging.events e
            INNER JOIN staging.matches m ON m.match_id = e.match_id
            WHERE m.competition_id = %s AND m.season_id = %s
            """
        ),
        "match_lineups (season)": (
            """
            SELECT COUNT(*) FROM staging.match_lineups ml
            INNER JOIN staging.matches m ON m.match_id = ml.match_id
            WHERE m.competition_id = %s AND m.season_id = %s
            """
        ),
    }
    with conn.cursor() as cur:
        print("\n--- staging counts ---")
        for name, sql in queries.items():
            if "%s" in sql:
                cur.execute(sql, (competition_id, season_id))
            else:
                cur.execute(sql)
            print(f"  {name:24s} {cur.fetchone()[0]:,}")


def print_analytics_counts(conn: PGConnection, competition_id: int, season_id: int) -> None:
    with conn.cursor() as cur:
        print("\n--- analytics counts ---")
        cur.execute(
            """
            SELECT COUNT(*) FROM analytics.fact_player_match_stats f
            INNER JOIN staging.matches m ON m.match_id = f.match_id
            WHERE m.competition_id = %s AND m.season_id = %s
            """,
            (competition_id, season_id),
        )
        fact_season = cur.fetchone()[0]
        print(f"  fact_player_match_stats   {fact_season:,} (season scope)")

        cur.execute(
            """
            SELECT COUNT(*) FROM analytics.team_match_formation f
            INNER JOIN staging.matches m ON m.match_id = f.match_id
            WHERE m.competition_id = %s AND m.season_id = %s
            """,
            (competition_id, season_id),
        )
        print(f"  team_match_formation      {cur.fetchone()[0]:,} (season scope)")

        cur.execute("SELECT COUNT(*) FROM analytics.fact_player_match_stats")
        print(f"  fact (all seasons)        {cur.fetchone()[0]:,}")

        cur.execute(
            """
            SELECT COUNT(*) FROM analytics.fact_player_match_stats f
            INNER JOIN staging.matches m ON m.match_id = f.match_id
            WHERE m.competition_id = %s AND m.season_id = %s AND f.team_id = %s
            """,
            (competition_id, season_id, KOREA_TEAM_ID),
        )
        print(f"  fact (Korea {KOREA_TEAM_ID}, season) {cur.fetchone()[0]:,}")


def fetch_compression_counts(
    conn: PGConnection, competition_id: int, season_id: int
) -> tuple[int, int]:
    """Return (staging.events rows, fact rows) for the given competition/season."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM staging.events e
            INNER JOIN staging.matches m ON m.match_id = e.match_id
            WHERE m.competition_id = %s AND m.season_id = %s
            """,
            (competition_id, season_id),
        )
        events_count = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*) FROM analytics.fact_player_match_stats f
            INNER JOIN staging.matches m ON m.match_id = f.match_id
            WHERE m.competition_id = %s AND m.season_id = %s
            """,
            (competition_id, season_id),
        )
        fact_count = cur.fetchone()[0]
    return events_count, fact_count


def print_compression_summary(conn: PGConnection, competition_id: int, season_id: int) -> None:
    """Evaluator demo: season-scoped raw vs aggregated row counts."""
    events_count, fact_count = fetch_compression_counts(conn, competition_id, season_id)
    ratio = events_count / fact_count if fact_count else 0
    print("\n--- compression (season scope) ---")
    print(f"  staging.events                    {events_count:>10,}")
    print(f"  analytics.fact_player_match_stats {fact_count:>10,}")
    if fact_count:
        print(f"  reduction                         ~{ratio:.0f}x")
