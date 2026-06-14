#!/usr/bin/env python3
"""Backward-compatible wrapper — use ``football-ingest`` after pip install."""
from football.cli.ingest import main

if __name__ == "__main__":
    raise SystemExit(main())
