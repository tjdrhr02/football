"""Table-by-table staging loaders (StatsBomb → PostgreSQL)."""
from __future__ import annotations

from typing import Iterable

import pandas as pd
from psycopg2.extensions import connection as PGConnection
from psycopg2.extras import Json, execute_values

from football.config import COMPETITION_ID, SEASON_ID
from football.ingest.statsbomb_client import (
    fetch_events,
    fetch_lineups,
    fetch_matches,
    fetch_wc_competition_row,
)
from football.ingest.transformers import (
    competition_row,
    event_row,
    lineup_rows,
    match_row,
    player_row,
    season_row,
    team_row,
)


def upsert_competition(conn: PGConnection, row: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO staging.competitions (
                competition_id, competition_name, country_name,
                competition_gender, data_source, ingested_at
            ) VALUES (%(competition_id)s, %(competition_name)s, %(country_name)s,
                      %(competition_gender)s, 'statsbomb_open', now())
            ON CONFLICT (competition_id) DO UPDATE SET
                competition_name = EXCLUDED.competition_name,
                country_name = EXCLUDED.country_name,
                competition_gender = EXCLUDED.competition_gender,
                ingested_at = now()
            """,
            row,
        )
    return 1


def upsert_season(conn: PGConnection, row: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO staging.seasons (competition_id, season_id, season_name)
            VALUES (%(competition_id)s, %(season_id)s, %(season_name)s)
            ON CONFLICT (competition_id, season_id) DO UPDATE SET
                season_name = EXCLUDED.season_name
            """,
            row,
        )
    return 1


def upsert_teams(conn: PGConnection, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        (
            r["team_id"],
            r["team_name"],
            r["team_gender"],
            r["country_name"],
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO staging.teams (
                team_id, team_name, team_gender, country_name, data_source, ingested_at
            ) VALUES %s
            ON CONFLICT (team_id) DO UPDATE SET
                team_name = EXCLUDED.team_name,
                team_gender = EXCLUDED.team_gender,
                country_name = EXCLUDED.country_name,
                ingested_at = now()
            """,
            values,
            template="(%s, %s, %s, %s, 'statsbomb_open', now())",
        )
    return len(rows)


def upsert_players(conn: PGConnection, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        (
            r["player_id"],
            r["player_name"],
            r["player_nickname"],
            r["country_name"],
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO staging.players (
                player_id, player_name, player_nickname, country_name,
                data_source, ingested_at
            ) VALUES %s
            ON CONFLICT (player_id) DO UPDATE SET
                player_name = EXCLUDED.player_name,
                player_nickname = EXCLUDED.player_nickname,
                country_name = EXCLUDED.country_name,
                ingested_at = now()
            """,
            values,
            template="(%s, %s, %s, %s, 'statsbomb_open', now())",
        )
    return len(rows)


def delete_events_for_match(conn: PGConnection, match_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM staging.events WHERE match_id = %s", (match_id,))


def delete_lineups_for_match(conn: PGConnection, match_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM staging.match_lineup_positions
            WHERE lineup_id IN (
                SELECT lineup_id FROM staging.match_lineups WHERE match_id = %s
            )
            """,
            (match_id,),
        )
        cur.execute("DELETE FROM staging.match_lineups WHERE match_id = %s", (match_id,))


def delete_match_children(conn: PGConnection, match_id: int) -> None:
    delete_lineups_for_match(conn, match_id)
    delete_events_for_match(conn, match_id)


def delete_season_matches(conn: PGConnection, competition_id: int, season_id: int) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT match_id FROM staging.matches
            WHERE competition_id = %s AND season_id = %s
            ORDER BY match_id
            """,
            (competition_id, season_id),
        )
        match_ids = [row[0] for row in cur.fetchall()]
        for match_id in match_ids:
            delete_match_children(conn, match_id)
        cur.execute(
            "DELETE FROM staging.matches WHERE competition_id = %s AND season_id = %s",
            (competition_id, season_id),
        )
    return match_ids


def teams_from_matches(matches_df: pd.DataFrame) -> list[dict]:
    teams: dict[int, dict] = {}
    for _, row in matches_df.iterrows():
        for prefix in ("home", "away"):
            team_id = int(row[f"{prefix}_team_id"])
            if team_id in teams:
                continue
            teams[team_id] = team_row(
                team_id=team_id,
                team_name=row[f"{prefix}_team"],
                team_gender=row.get(f"{prefix}_team_gender"),
                country_name=row.get(f"{prefix}_team_country_name"),
            )
    return list(teams.values())


def players_from_lineups(lineups: dict[str, pd.DataFrame]) -> list[dict]:
    players: dict[int, dict] = {}
    for df in lineups.values():
        for _, row in df.iterrows():
            pid = int(row["player_id"])
            if pid not in players:
                players[pid] = player_row(row)
    return list(players.values())


def load_competitions(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
) -> int:
    row = competition_row(fetch_wc_competition_row(competition_id, season_id))
    return upsert_competition(conn, row)


def load_seasons(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
) -> int:
    row = season_row(fetch_wc_competition_row(competition_id, season_id))
    return upsert_season(conn, row)


def load_teams(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    matches_df: pd.DataFrame | None = None,
) -> int:
    if matches_df is None:
        matches_df = fetch_matches(competition_id, season_id)
    return upsert_teams(conn, teams_from_matches(matches_df))


def load_players(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    match_ids: Iterable[int] | None = None,
    matches_df: pd.DataFrame | None = None,
) -> int:
    if matches_df is None:
        matches_df = fetch_matches(competition_id, season_id)
    if match_ids is None:
        match_ids = matches_df["match_id"].astype(int).tolist()

    players: dict[int, dict] = {}
    for match_id in match_ids:
        lineups = fetch_lineups(int(match_id))
        for row in players_from_lineups(lineups):
            players[row["player_id"]] = row
    return upsert_players(conn, list(players.values()))


def load_matches(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    matches_df: pd.DataFrame | None = None,
    match_ids: Iterable[int] | None = None,
    replace: bool = True,
) -> int:
    if matches_df is None:
        matches_df = fetch_matches(competition_id, season_id)
    if match_ids is not None:
        match_ids = [int(mid) for mid in match_ids]
        matches_df = matches_df[matches_df["match_id"].isin(match_ids)].copy()
        found_ids = set(matches_df["match_id"].astype(int).tolist())
        missing_ids = sorted(set(match_ids) - found_ids)
        if missing_ids:
            raise ValueError(f"match_ids not found for competition/season: {missing_ids}")

    if replace:
        if match_ids is None:
            delete_season_matches(conn, competition_id, season_id)
        else:
            for match_id in match_ids:
                delete_match_children(conn, match_id)
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM staging.matches WHERE match_id = %s",
                        (match_id,),
                    )

    rows = [match_row(row) for _, row in matches_df.iterrows()]
    values = [
        (
            r["match_id"],
            r["competition_id"],
            r["season_id"],
            r["match_date"],
            r["kick_off"],
            r["home_team_id"],
            r["away_team_id"],
            r["home_score"],
            r["away_score"],
            r["match_status"],
            r["competition_stage"],
            r["match_week"],
            r["stadium_name"],
            r["referee_name"],
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO staging.matches (
                match_id, competition_id, season_id, match_date, kick_off,
                home_team_id, away_team_id, home_score, away_score, match_status,
                competition_stage, match_week, stadium_name, referee_name,
                data_source, ingested_at
            ) VALUES %s
            """,
            values,
            template=(
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "'statsbomb_open', now())"
            ),
        )
    return len(rows)


def load_events(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    match_ids: Iterable[int] | None = None,
    matches_df: pd.DataFrame | None = None,
) -> int:
    if matches_df is None:
        matches_df = fetch_matches(competition_id, season_id)
    if match_ids is None:
        match_ids = matches_df["match_id"].astype(int).tolist()

    total = 0
    for match_id in match_ids:
        total += load_events_for_match(conn, int(match_id))
    return total


def load_events_for_match(conn: PGConnection, match_id: int) -> int:
    delete_events_for_match(conn, match_id)
    events_df = fetch_events(match_id)
    if events_df.empty:
        return 0

    rows = [event_row(row, match_id) for _, row in events_df.iterrows()]
    values = [
        (
            str(r["event_id"]),
            r["match_id"],
            r["index"],
            r["period"],
            r["timestamp"],
            r["minute"],
            r["second"],
            r["type"],
            r["team_id"],
            r["player_id"],
            r["location_x"],
            r["location_y"],
            r["duration"],
            r["under_pressure"],
            r["outcome"],
            r["shot_statsbomb_xg"],
            Json(r["payload"]),
        )
        for r in rows
    ]

    with conn.cursor() as cur:
        execute_values(
            cur,
            """
            INSERT INTO staging.events (
                event_id, match_id, index, period, timestamp, minute, second,
                type, team_id, player_id, location_x, location_y, duration,
                under_pressure, outcome, shot_statsbomb_xg, payload, ingested_at
            ) VALUES %s
            """,
            values,
            template=(
                "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())"
            ),
            page_size=500,
        )
    return len(rows)


def _team_id_from_lineups(match_id: int, team_name: str, matches_df: pd.DataFrame) -> int:
    match = matches_df.loc[matches_df["match_id"] == match_id].iloc[0]
    if match["home_team"] == team_name:
        return int(match["home_team_id"])
    if match["away_team"] == team_name:
        return int(match["away_team_id"])
    raise ValueError(f"team '{team_name}' not in match {match_id}")


def load_match_lineups(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    match_ids: Iterable[int] | None = None,
    matches_df: pd.DataFrame | None = None,
) -> tuple[int, int]:
    if matches_df is None:
        matches_df = fetch_matches(competition_id, season_id)
    if match_ids is None:
        match_ids = matches_df["match_id"].astype(int).tolist()

    lineup_count = 0
    position_count = 0
    for match_id in match_ids:
        lc, pc = load_match_lineups_for_match(conn, int(match_id), matches_df)
        lineup_count += lc
        position_count += pc
    return lineup_count, position_count


def load_match_lineups_for_match(
    conn: PGConnection,
    match_id: int,
    matches_df: pd.DataFrame,
) -> tuple[int, int]:
    delete_lineups_for_match(conn, match_id)

    lineups_api = fetch_lineups(match_id)
    all_lineups: list[dict] = []
    all_positions: list[dict] = []

    for team_name, df in lineups_api.items():
        team_id = _team_id_from_lineups(match_id, team_name, matches_df)
        lineups, positions = lineup_rows(match_id, team_id, df)
        all_lineups.extend(lineups)
        all_positions.extend(positions)

    if not all_lineups:
        return 0, 0

    lineup_id_by_player: dict[int, int] = {}
    with conn.cursor() as cur:
        for lineup in all_lineups:
            cur.execute(
                """
                INSERT INTO staging.match_lineups (
                    match_id, team_id, player_id, jersey_number, is_starter
                ) VALUES (%(match_id)s, %(team_id)s, %(player_id)s,
                          %(jersey_number)s, %(is_starter)s)
                RETURNING lineup_id
                """,
                lineup,
            )
            lineup_id = cur.fetchone()[0]
            lineup_id_by_player[lineup["player_id"]] = lineup_id

        position_values = []
        for pos in all_positions:
            lineup_id = lineup_id_by_player[pos["player_id"]]
            position_values.append(
                (
                    lineup_id,
                    pos["position_name"],
                    pos["statsbomb_position_id"],
                    pos["from_period"],
                    pos["from_minute"],
                    pos["to_period"],
                    pos["to_minute"],
                    pos["start_reason"],
                    pos["end_reason"],
                )
            )

        execute_values(
            cur,
            """
            INSERT INTO staging.match_lineup_positions (
                lineup_id, position_name, statsbomb_position_id,
                from_period, from_minute, to_period, to_minute,
                start_reason, end_reason
            ) VALUES %s
            """,
            position_values,
        )

    return len(all_lineups), len(all_positions)
