"""Load StatsBomb WC2022 data into staging tables (table-by-table)."""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import bootstrap

bootstrap()

from football.config import COMPETITION_ID, DEFAULT_DB, SEASON_ID
from football.db.connection import transaction
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


def start_ingestion_run(conn, competition_id: int, season_id: int) -> int:
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
    conn,
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


def print_counts(conn, competition_id: int, season_id: int) -> None:
    queries = {
        "competitions": "SELECT COUNT(*) FROM staging.competitions",
        "seasons": "SELECT COUNT(*) FROM staging.seasons",
        "teams": "SELECT COUNT(*) FROM staging.teams",
        "players": "SELECT COUNT(*) FROM staging.players",
        "matches": (
            "SELECT COUNT(*) FROM staging.matches "
            "WHERE competition_id = %s AND season_id = %s"
        ),
        "events": "SELECT COUNT(*) FROM staging.events",
        "match_lineups": "SELECT COUNT(*) FROM staging.match_lineups",
        "match_lineup_positions": "SELECT COUNT(*) FROM staging.match_lineup_positions",
    }
    with conn.cursor() as cur:
        print("\n--- staging counts ---")
        for name, sql in queries.items():
            if "%s" in sql:
                cur.execute(sql, (competition_id, season_id))
            else:
                cur.execute(sql)
            print(f"  {name:24s} {cur.fetchone()[0]:,}")


def run_table(
    conn,
    table: str,
    competition_id: int,
    season_id: int,
    match_ids: list[int] | None,
    matches_df,
) -> tuple[int, int]:
    """Return (matches_processed, events_processed) counters."""
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
            n = load_events_for_match(conn, match_ids[0])
            events_processed = n
            matches_processed = 1
            print(f"[ok] events (match {match_ids[0]}): {n:,} row(s)")
        else:
            n = load_events(
                conn,
                competition_id,
                season_id,
                match_ids=match_ids,
                matches_df=matches_df,
            )
            events_processed = n
            matches_processed = len(match_ids) if match_ids else len(matches_df)
            print(f"[ok] events: {n:,} row(s)")
    elif table == "lineups":
        if match_ids and len(match_ids) == 1:
            lc, pc = load_match_lineups_for_match(conn, match_ids[0], matches_df)
            matches_processed = 1
            print(f"[ok] lineups (match {match_ids[0]}): {lc} squads, {pc} positions")
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


def run_pipeline(
    conn,
    table: str,
    competition_id: int,
    season_id: int,
    match_ids: list[int] | None,
) -> tuple[int, int]:
    """Run one or all ingest steps. Returns (matches_processed, events_processed)."""
    matches_df = fetch_matches(competition_id, season_id)
    if match_ids:
        matches_df = matches_df[matches_df["match_id"].isin(match_ids)].copy()
        if matches_df.empty:
            raise ValueError(f"no matches found for ids: {match_ids}")

    total_matches = 0
    total_events = 0

    if table == "all":
        order = ("competitions", "seasons", "teams", "players", "matches", "events", "lineups")
        for step in order:
            m, e = run_table(conn, step, competition_id, season_id, match_ids, matches_df)
            total_matches = max(total_matches, m)
            total_events += e
    else:
        total_matches, total_events = run_table(
            conn, table, competition_id, season_id, match_ids, matches_df
        )

    return total_matches, total_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest StatsBomb WC2022 into staging")
    parser.add_argument(
        "--table",
        choices=TABLE_STEPS,
        default="all",
        help="Load a single staging table (or all in FK order)",
    )
    parser.add_argument("--competition-id", type=int, default=COMPETITION_ID)
    parser.add_argument("--season-id", type=int, default=SEASON_ID)
    parser.add_argument("--dbname", default=DEFAULT_DB)
    parser.add_argument(
        "--match-id",
        type=int,
        action="append",
        dest="match_ids",
        help="Limit events/lineups/players to specific match(es)",
    )
    parser.add_argument(
        "--no-run-log",
        action="store_true",
        help="Skip staging.ingestion_runs bookkeeping",
    )
    parser.add_argument(
        "--counts-only",
        action="store_true",
        help="Print staging row counts and exit",
    )
    args = parser.parse_args()

    if args.counts_only:
        try:
            with transaction(args.dbname) as conn:
                print_counts(conn, args.competition_id, args.season_id)
            return 0
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1

    try:
        run_id = None
        if not args.no_run_log:
            with transaction(args.dbname) as conn:
                run_id = start_ingestion_run(conn, args.competition_id, args.season_id)

        try:
            with transaction(args.dbname) as conn:
                matches_processed, events_processed = run_pipeline(
                    conn,
                    args.table,
                    args.competition_id,
                    args.season_id,
                    args.match_ids,
                )
                print_counts(conn, args.competition_id, args.season_id)
        except Exception as exc:
            if run_id is not None:
                with transaction(args.dbname) as conn:
                    finish_ingestion_run(conn, run_id, "failed", error_message=str(exc))
            raise

        if run_id is not None:
            with transaction(args.dbname) as conn:
                finish_ingestion_run(
                    conn,
                    run_id,
                    "success",
                    matches_processed=matches_processed,
                    events_processed=events_processed,
                )

    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
