"""Ensure ``src/`` is on ``sys.path`` when scripts run without ``pip install -e .``."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def bootstrap() -> Path:
    src = str(SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    return ROOT
