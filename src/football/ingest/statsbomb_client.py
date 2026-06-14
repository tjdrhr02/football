"""Fetch StatsBomb Open Data for WC2022 ingest."""
from __future__ import annotations

import pandas as pd
from statsbombpy import sb

from football.config import COMPETITION_ID, SEASON_ID


def fetch_wc_competition_row(
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
) -> pd.Series:
    comps = sb.competitions()
    wc = comps[(comps["competition_id"] == competition_id) & (comps["season_id"] == season_id)]
    if wc.empty:
        raise ValueError(f"competition_id={competition_id}, season_id={season_id} not found")
    return wc.iloc[0]


def fetch_matches(
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
) -> pd.DataFrame:
    return sb.matches(competition_id=competition_id, season_id=season_id)


def fetch_events(match_id: int) -> pd.DataFrame:
    return sb.events(match_id=int(match_id))


def fetch_lineups(match_id: int) -> dict[str, pd.DataFrame]:
    return sb.lineups(match_id=int(match_id))
