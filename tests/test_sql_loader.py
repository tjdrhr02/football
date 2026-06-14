"""Tests for SQL file loading."""

from football.sql_loader import load_sql


def test_load_aggregate_sql_files_exist():
    fact = load_sql("aggregate", "fact_player_match_stats.sql")
    formation = load_sql("aggregate", "team_match_formation.sql")

    assert "INSERT INTO analytics.fact_player_match_stats" in fact
    assert "INSERT INTO analytics.team_match_formation" in formation
    assert "scoped_matches" in fact
    assert "scoped_matches" in formation
