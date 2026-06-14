"""staging → analytics aggregation."""

from football.aggregation.fact_player_match_stats import aggregate_fact_player_match_stats
from football.aggregation.team_match_formation import aggregate_team_match_formation

__all__ = [
    "aggregate_fact_player_match_stats",
    "aggregate_team_match_formation",
]
