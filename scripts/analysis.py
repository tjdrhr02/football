#!/usr/bin/env python3
"""Backward-compatible wrapper — use ``football-analysis`` after pip install."""
from football.cli.analysis import main

if __name__ == "__main__":
    raise SystemExit(main())
