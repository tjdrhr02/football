#!/usr/bin/env python3
"""Backward-compatible wrapper — use ``football-aggregate`` after pip install."""
from football.cli.aggregate import main

if __name__ == "__main__":
    raise SystemExit(main())
