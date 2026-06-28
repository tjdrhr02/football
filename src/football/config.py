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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = PROJECT_ROOT / "db" / "schema"
PACKAGE_DIR = Path(__file__).resolve().parent
SQL_DIR = PACKAGE_DIR / "sql"

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
BRAZIL_TEAM_ID = 781  # Day 5 matchup opponent (Round of 16, match_id=3869253)

# RAG embeddings (Day 4) — local sentence-transformers (zero cost, offline, no API key)
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))
# bge-* retrieval: prepend this instruction to QUERIES only (not documents)
EMBED_QUERY_INSTRUCTION = os.getenv(
    "EMBED_QUERY_INSTRUCTION",
    "Represent this sentence for searching relevant passages: ",
)

# LLM generation (Day 5) — Google Gemini, free tier
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

DEFAULT_DB = str(DB_CONFIG["dbname"])


def db_config(dbname: str | None = None) -> dict[str, object]:
    """Return a psycopg2 connection dict, optionally overriding ``dbname``."""
    cfg = dict(DB_CONFIG)
    if dbname is not None:
        cfg["dbname"] = dbname
    return cfg
