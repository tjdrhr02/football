"""Project settings: PostgreSQL connection and StatsBomb WC2022 seed data."""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")


_load_dotenv()

DB_CONFIG: dict[str, object] = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "football"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", ""),
}

# StatsBomb Open Data — 2022 FIFA World Cup
COMPETITION_ID = 43  # FIFA World Cup
SEASON_ID = 106  # 2022
KOREA_TEAM_ID = 791

DEFAULT_DB = str(DB_CONFIG["dbname"])


def db_config(dbname: str | None = None) -> dict[str, object]:
    """Return a psycopg2 connection dict, optionally overriding ``dbname``."""
    cfg = dict(DB_CONFIG)
    if dbname is not None:
        cfg["dbname"] = dbname
    return cfg
