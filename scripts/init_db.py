"""Apply db/schema/*.sql to a local PostgreSQL database."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import bootstrap

ROOT = bootstrap()

from football.config import DEFAULT_DB, db_config

SCHEMA_DIR = ROOT / "db" / "schema"


def schema_files() -> list:
    files = sorted(SCHEMA_DIR.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"No SQL files in {SCHEMA_DIR}")
    return files


def ensure_database(dbname: str) -> None:
    conn = psycopg2.connect(**db_config("postgres"))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone():
                print(f"[skip] database '{dbname}' already exists")
                return
            cur.execute(f'CREATE DATABASE "{dbname}"')
            print(f"[ok] created database '{dbname}'")
    finally:
        conn.close()


def run_sql_file(conn, path) -> None:
    sql = path.read_text(encoding="utf-8")
    print(f"[run] {path.relative_to(ROOT)}")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def init_db(dbname: str, recreate: bool = False) -> None:
    if recreate:
        conn = psycopg2.connect(**db_config("postgres"))
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (dbname,),
                )
                cur.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
                print(f"[ok] dropped database '{dbname}'")
        finally:
            conn.close()

    ensure_database(dbname)

    conn = psycopg2.connect(**db_config(dbname))
    try:
        for path in schema_files():
            run_sql_file(conn, path)
    finally:
        conn.close()

    print(f"[done] schema applied to '{dbname}'")


def verify(dbname: str) -> None:
    expected = {
        "staging": {
            "competitions",
            "seasons",
            "teams",
            "players",
            "matches",
            "events",
            "match_lineups",
            "match_lineup_positions",
            "ingestion_runs",
        },
        "analytics": {
            "fact_player_match_stats",
            "team_match_formation",
            "embedding_documents",
        },
    }
    conn = psycopg2.connect(**db_config(dbname))
    try:
        with conn.cursor() as cur:
            for schema, tables in expected.items():
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """,
                    (schema,),
                )
                found = {row[0] for row in cur.fetchall()}
                missing = tables - found
                extra = found - tables
                if missing:
                    raise RuntimeError(f"{schema}: missing tables {sorted(missing)}")
                print(f"[verify] {schema}: {len(found)} tables OK")
                if extra:
                    print(f"  [info] extra tables: {sorted(extra)}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize PostgreSQL schema from db/schema/*.sql")
    parser.add_argument("--dbname", default=DEFAULT_DB, help=f"Database name (default: {DEFAULT_DB})")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the database before applying schema",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify expected tables exist",
    )
    args = parser.parse_args()

    try:
        if args.verify_only:
            verify(args.dbname)
        else:
            init_db(args.dbname, recreate=args.recreate)
            verify(args.dbname)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
