"""Unified StatsBomb pipeline CLI (same as project-root ``run_pipeline.py``)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import bootstrap

bootstrap()

from football.pipeline.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
