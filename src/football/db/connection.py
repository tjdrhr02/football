"""psycopg2 connection helpers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extensions import connection as PGConnection

from football.config import db_config


def get_connection(dbname: str | None = None) -> PGConnection:
    """Open a new PostgreSQL connection."""
    return psycopg2.connect(**db_config(dbname))


@contextmanager
def transaction(dbname: str | None = None) -> Generator[PGConnection, None, None]:
    """Context manager: commit on success, rollback on error, always close."""
    conn = get_connection(dbname)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
