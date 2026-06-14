"""Unit tests for ingest transformers."""

from __future__ import annotations

import math

import pandas as pd

from football.ingest.transformers import (
    clean_value,
    parse_clock_minute,
    unified_outcome,
)


def test_clean_value_nan_and_empty_string():
    assert clean_value(float("nan")) is None
    assert clean_value("") is None
    assert clean_value("  ") is None
    assert clean_value(42) == 42
    assert clean_value("goal") == "goal"


def test_parse_clock_minute():
    assert parse_clock_minute("64:10") == 64
    assert parse_clock_minute("0:00") == 0
    assert parse_clock_minute(45) == 45
    assert parse_clock_minute(None) is None


def test_unified_outcome_pass_and_shot():
    pass_row = pd.Series({"type": "Pass", "pass_outcome": None, "shot_outcome": None})
    assert unified_outcome(pass_row) is None

    shot_row = pd.Series({"type": "Shot", "pass_outcome": None, "shot_outcome": "Goal"})
    assert unified_outcome(shot_row) == "Goal"

    incomplete_pass = pd.Series({"type": "Pass", "pass_outcome": "Incomplete", "shot_outcome": None})
    assert unified_outcome(incomplete_pass) == "Incomplete"


def test_clean_value_numpy_scalar():
    import numpy as np

    assert clean_value(np.int64(7)) == 7
    assert clean_value(np.float64(math.nan)) is None
