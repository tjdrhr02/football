"""StatsBomb API rows → staging table rows."""
from __future__ import annotations

import math
from datetime import date, time
from typing import Any
from uuid import UUID

import pandas as pd

EVENT_CORE_COLUMNS = frozenset(
    {
        "id",
        "match_id",
        "index",
        "period",
        "timestamp",
        "minute",
        "second",
        "type",
        "team_id",
        "player_id",
        "location",
        "duration",
        "under_pressure",
        "pass_outcome",
        "shot_outcome",
        "shot_statsbomb_xg",
    }
)


def clean_value(value: Any) -> Any:
    """Convert pandas/numpy sentinels to psycopg2-friendly Python values."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, dict)):
        return value
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        if pd.isna(value):
            return None
    except (ValueError, TypeError):
        return value
    if hasattr(value, "item") and isinstance(value, (pd.Timestamp,)):
        return value.to_pydatetime()
    if hasattr(value, "item") and type(value).__module__ == "numpy":
        native = value.item()
        if isinstance(native, float) and math.isnan(native):
            return None
        return native
    return value


def parse_clock_minute(clock: Any) -> int | None:
    """Parse StatsBomb clock strings like ``'64:10'`` → minute component."""
    clock = clean_value(clock)
    if clock is None:
        return None
    text = str(clock)
    if ":" in text:
        return int(text.split(":")[0])
    return int(text)


def competition_row(row: pd.Series) -> dict[str, Any]:
    return {
        "competition_id": int(row["competition_id"]),
        "competition_name": str(row["competition_name"]),
        "country_name": clean_value(row.get("country_name")),
        "competition_gender": clean_value(row.get("competition_gender")),
    }


def season_row(row: pd.Series) -> dict[str, Any]:
    return {
        "competition_id": int(row["competition_id"]),
        "season_id": int(row["season_id"]),
        "season_name": str(row["season_name"]),
    }


def team_row(
    team_id: int,
    team_name: str,
    team_gender: Any = None,
    country_name: Any = None,
) -> dict[str, Any]:
    return {
        "team_id": int(team_id),
        "team_name": str(team_name),
        "team_gender": clean_value(team_gender),
        "country_name": clean_value(country_name),
    }


def player_row(row: pd.Series) -> dict[str, Any]:
    return {
        "player_id": int(row["player_id"]),
        "player_name": str(row["player_name"]),
        "player_nickname": clean_value(row.get("player_nickname")),
        "country_name": clean_value(row.get("country")),
    }


def match_row(row: pd.Series) -> dict[str, Any]:
    match_date = row["match_date"]
    if isinstance(match_date, str):
        match_date = date.fromisoformat(match_date)
    elif hasattr(match_date, "date"):
        match_date = match_date.date()

    kick_off = clean_value(row.get("kick_off"))
    if isinstance(kick_off, str):
        kick_off = time.fromisoformat(kick_off.split(".")[0])

    return {
        "match_id": int(row["match_id"]),
        "competition_id": int(row["competition_id"]),
        "season_id": int(row["season_id"]),
        "match_date": match_date,
        "kick_off": kick_off,
        "home_team_id": int(row["home_team_id"]),
        "away_team_id": int(row["away_team_id"]),
        "home_score": clean_value(row.get("home_score")),
        "away_score": clean_value(row.get("away_score")),
        "match_status": clean_value(row.get("match_status")),
        "competition_stage": str(row["competition_stage"]),
        "match_week": clean_value(row.get("match_week")),
        "stadium_name": clean_value(row.get("stadium")),
        "referee_name": clean_value(row.get("referee")),
    }


def _json_safe(value: Any) -> Any:
    value = clean_value(value)
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items() if _json_safe(v) is not None}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value if _json_safe(v) is not None]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def event_payload(row: pd.Series) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for col in row.index:
        if col in EVENT_CORE_COLUMNS:
            continue
        val = _json_safe(row[col])
        if val is not None:
            payload[str(col)] = val
    return payload


def unified_outcome(row: pd.Series) -> str | None:
    event_type = row.get("type")
    if event_type == "Pass":
        return clean_value(row.get("pass_outcome"))
    if event_type == "Shot":
        return clean_value(row.get("shot_outcome"))
    return clean_value(row.get("pass_outcome")) or clean_value(row.get("shot_outcome"))


def event_row(row: pd.Series, match_id: int) -> dict[str, Any]:
    location = row.get("location")
    location_x = location_y = None
    if isinstance(location, (list, tuple)) and len(location) == 2:
        location_x = float(location[0])
        location_y = float(location[1])

    payload = event_payload(row)
    return {
        "event_id": UUID(str(row["id"])),
        "match_id": int(match_id),
        "index": int(row["index"]),
        "period": int(row["period"]),
        "timestamp": clean_value(row.get("timestamp")),
        "minute": clean_value(row.get("minute")),
        "second": clean_value(row.get("second")),
        "type": str(row["type"]),
        "team_id": clean_value(row.get("team_id")),
        "player_id": clean_value(row.get("player_id")),
        "location_x": location_x,
        "location_y": location_y,
        "duration": clean_value(row.get("duration")),
        "under_pressure": clean_value(row.get("under_pressure")),
        "outcome": unified_outcome(row),
        "shot_statsbomb_xg": clean_value(row.get("shot_statsbomb_xg")),
        "payload": payload,
    }


def lineup_rows(
    match_id: int,
    team_id: int,
    lineup_df: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (match_lineups rows, match_lineup_positions rows without lineup_id)."""
    lineups: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []

    for _, row in lineup_df.iterrows():
        pos_list = row.get("positions") or []
        if not isinstance(pos_list, list):
            pos_list = []

        is_starter = any(p.get("start_reason") == "Starting XI" for p in pos_list)
        lineup = {
            "match_id": int(match_id),
            "team_id": int(team_id),
            "player_id": int(row["player_id"]),
            "jersey_number": clean_value(row.get("jersey_number")),
            "is_starter": bool(is_starter),
        }
        lineups.append(lineup)

        for pos in pos_list:
            positions.append(
                {
                    "player_id": int(row["player_id"]),
                    "position_name": str(pos["position"]),
                    "statsbomb_position_id": clean_value(pos.get("position_id")),
                    "from_period": clean_value(pos.get("from_period")),
                    "from_minute": parse_clock_minute(pos.get("from")),
                    "to_period": clean_value(pos.get("to_period")),
                    "to_minute": parse_clock_minute(pos.get("to")),
                    "start_reason": clean_value(pos.get("start_reason")),
                    "end_reason": clean_value(pos.get("end_reason")),
                }
            )

    return lineups, positions
