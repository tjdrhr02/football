#!/usr/bin/env python3
"""Unified StatsBomb pipeline entry point (evaluator demo).

Prefer: ``football-pipeline`` after ``pip install -e .``
"""
from __future__ import annotations

from football.pipeline.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
