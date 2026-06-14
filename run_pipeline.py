#!/usr/bin/env python3
"""Unified StatsBomb pipeline entry point (evaluator demo).

Usage:
    .venv/bin/python run_pipeline.py --competition-id 43 --season-id 106
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from bootstrap import bootstrap

bootstrap()

from football.pipeline.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
