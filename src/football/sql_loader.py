"""Load versioned SQL files from the repository ``sql/`` tree."""
from __future__ import annotations

from football.config import SQL_DIR


def load_sql(*parts: str) -> str:
    path = SQL_DIR.joinpath(*parts)
    if not path.is_file():
        raise FileNotFoundError(f"SQL file not found: {path}")
    return path.read_text(encoding="utf-8")
