"""Staging ingest orchestration (StatsBomb → PostgreSQL)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import pandas as pd
from psycopg2.extensions import connection as PGConnection

from football.aggregation.common import delete_analytics_for_matches, delete_analytics_for_season
from football.ingest.loaders import (
    load_competitions,
    load_events,
    load_events_for_match,
    load_match_lineups,
    load_match_lineups_for_match,
    load_matches,
    load_players,
    load_seasons,
    load_teams,
)
from football.ingest.statsbomb_client import fetch_matches

TABLE_STEPS = (
    "competitions",
    "seasons",
    "teams",
    "players",
    "matches",
    "events",
    "lineups",
    "all",
)

MatchEventsCallback = Callable[[int, int, int, int], None]


def _resolve_matches_df(
    competition_id: int,
    season_id: int,
    match_ids: list[int] | None,
) -> pd.DataFrame:
    matches_df = fetch_matches(competition_id, season_id)
    if match_ids:
        matches_df = matches_df[matches_df["match_id"].isin(match_ids)].copy()
        if matches_df.empty:
            raise ValueError(f"no matches found for ids: {match_ids}")
    return matches_df


def run_staging_table(
    conn: PGConnection,
    table: str,
    competition_id: int,
    season_id: int,
    match_ids: list[int] | None,
    matches_df: pd.DataFrame,
    *,
    verbose: bool = False,
    on_match_events: MatchEventsCallback | None = None,
) -> tuple[int, int]:
    """Run one ingest step. Returns (matches_processed, events_processed)."""
    matches_processed = 0
    events_processed = 0

    if table == "competitions":
        n = load_competitions(conn, competition_id, season_id)
        print(f"[ok] competitions: {n} row(s)")
    elif table == "seasons":
        n = load_seasons(conn, competition_id, season_id)
        print(f"[ok] seasons: {n} row(s)")
    elif table == "teams":
        n = load_teams(conn, competition_id, season_id, matches_df=matches_df)
        print(f"[ok] teams: {n} row(s)")
    elif table == "players":
        n = load_players(
            conn,
            competition_id,
            season_id,
            match_ids=match_ids,
            matches_df=matches_df,
        )
        print(f"[ok] players: {n} row(s)")
    elif table == "matches":
        n = load_matches(
            conn,
            competition_id,
            season_id,
            matches_df=matches_df,
            match_ids=match_ids,
            replace=True,
        )
        matches_processed = n
        print(f"[ok] matches: {n} row(s)")
    elif table == "events":
        if match_ids and len(match_ids) == 1:
            match_id = match_ids[0]
            n = load_events_for_match(conn, match_id)
            events_processed = n
            matches_processed = 1
            if verbose:
                print(f"[1/1] match_id={match_id}: {n:,}행 적재")
                print(f"✓ events 적재 완료: 총 {n:,}행")
            else:
                print(f"[ok] events (match {match_id}): {n:,} row(s)")
        else:
            callback = on_match_events
            if verbose and callback is None:

                def callback(i: int, total: int, match_id: int, rows: int) -> None:
                    print(f"[{i}/{total}] match_id={match_id}: {rows:,}행 적재")

            n = load_events(
                conn,
                competition_id,
                season_id,
                match_ids=match_ids,
                matches_df=matches_df,
                on_match_loaded=callback,
            )
            events_processed = n
            matches_processed = len(match_ids) if match_ids else len(matches_df)
            if verbose:
                print(f"✓ events 적재 완료: 총 {n:,}행")
            else:
                print(f"[ok] events: {n:,} row(s)")
    elif table == "lineups":
        if match_ids and len(match_ids) == 1:
            match_id = match_ids[0]
            lc, pc = load_match_lineups_for_match(conn, match_id, matches_df)
            matches_processed = 1
            print(f"[ok] lineups (match {match_id}): {lc} squads, {pc} positions")
        else:
            lc, pc = load_match_lineups(
                conn,
                competition_id,
                season_id,
                match_ids=match_ids,
                matches_df=matches_df,
            )
            matches_processed = len(match_ids) if match_ids else len(matches_df)
            print(f"[ok] lineups: {lc} squads, {pc} positions")
    else:
        raise ValueError(f"unknown table step: {table}")

    return matches_processed, events_processed


def run_staging_ingest(
    conn: PGConnection,
    table: Literal[
        "competitions",
        "seasons",
        "teams",
        "players",
        "matches",
        "events",
        "lineups",
        "all",
    ],
    competition_id: int,
    season_id: int,
    match_ids: list[int] | None = None,
    *,
    verbose: bool = False,
    on_match_events: MatchEventsCallback | None = None,
) -> tuple[int, int]:
    """Run one or all staging ingest steps. Returns (matches_processed, events_processed)."""
    matches_df = _resolve_matches_df(competition_id, season_id, match_ids)

    # analytics FK → staging.matches: clear fact/formation before match DELETE/replace
    if table in ("all", "matches"):
        if match_ids:
            delete_analytics_for_matches(conn, [int(mid) for mid in match_ids])
        else:
            delete_analytics_for_season(conn, competition_id, season_id, match_ids=None)

    total_matches = 0
    total_events = 0

    if table == "all":
        order = ("competitions", "seasons", "teams", "players", "matches", "events", "lineups")
        for step in order:
            m, e = run_staging_table(
                conn,
                step,
                competition_id,
                season_id,
                match_ids,
                matches_df,
                verbose=verbose,
                on_match_events=on_match_events,
            )
            total_matches = max(total_matches, m)
            total_events += e
    else:
        total_matches, total_events = run_staging_table(
            conn,
            table,
            competition_id,
            season_id,
            match_ids,
            matches_df,
            verbose=verbose,
            on_match_events=on_match_events,
        )

    return total_matches, total_events
