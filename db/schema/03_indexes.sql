-- Performance indexes (Phase 1 Step 4)
-- Source: AGENTS.md §6, db/erd.dbml
-- Apply after 02_analytics.sql. Safe to re-run (IF NOT EXISTS).

-- analytics.fact_player_match_stats — analysis queries
CREATE INDEX IF NOT EXISTS idx_fpms_player_match
    ON analytics.fact_player_match_stats (player_id, match_id);

CREATE INDEX IF NOT EXISTS idx_fpms_team_match
    ON analytics.fact_player_match_stats (team_id, match_id);

CREATE INDEX IF NOT EXISTS idx_fpms_cover
    ON analytics.fact_player_match_stats (player_id, match_id)
    INCLUDE (xg, passes_attempted, passes_completed, pass_completion_rate, minutes_played);

-- staging.events — ETL aggregation (match-scoped type/player filters)
CREATE INDEX IF NOT EXISTS idx_events_match_type_player
    ON staging.events (match_id, type, player_id);

-- analytics.team_match_formation — timeline lookups
CREATE INDEX IF NOT EXISTS idx_tmf_timeline
    ON analytics.team_match_formation (match_id, team_id, from_minute);
