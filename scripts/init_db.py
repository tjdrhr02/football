#!/usr/bin/env python3
"""Backward-compatible wrapper — use ``football-init-db`` after pip install."""
from football.cli.init_db import main

if __name__ == "__main__":
    raise SystemExit(main())
