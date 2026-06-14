"""StatsBomb → staging ingest."""

from football.ingest.loaders import (
    load_competitions,
    load_events,
    load_match_lineups,
    load_matches,
    load_players,
    load_seasons,
    load_teams,
)

__all__ = [
    "load_competitions",
    "load_seasons",
    "load_teams",
    "load_players",
    "load_matches",
    "load_events",
    "load_match_lineups",
]
