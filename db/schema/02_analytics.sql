-- analytics (Gold) — aggregates and RAG
-- Source: db/erd.dbml
-- Performance indexes (idx_fpms_*, idx_events_*, HNSW) → db/schema/03_indexes.sql (later)

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE analytics.fact_player_match_stats (
    match_id              INTEGER NOT NULL
        REFERENCES staging.matches (match_id),
    player_id             INTEGER NOT NULL
        REFERENCES staging.players (player_id),
    team_id               INTEGER NOT NULL
        REFERENCES staging.teams (team_id),
    minutes_played        DECIMAL(6, 2) NOT NULL DEFAULT 0,
    is_starter            BOOLEAN NOT NULL DEFAULT FALSE,
    position_played       VARCHAR,
    passes_attempted      INTEGER NOT NULL DEFAULT 0,
    passes_completed      INTEGER NOT NULL DEFAULT 0,
    pass_completion_rate  DECIMAL(5, 4),
    progressive_passes    INTEGER DEFAULT 0,
    shots                 INTEGER NOT NULL DEFAULT 0,
    shots_on_target       INTEGER NOT NULL DEFAULT 0,
    goals                 INTEGER NOT NULL DEFAULT 0,
    assists               INTEGER NOT NULL DEFAULT 0,
    xg                    DECIMAL(6, 4) DEFAULT 0,
    xa                    DECIMAL(6, 4) DEFAULT 0,
    tackles               INTEGER DEFAULT 0,
    interceptions         INTEGER DEFAULT 0,
    pressures             INTEGER DEFAULT 0,
    blocks                INTEGER DEFAULT 0,
    dribbles_attempted    INTEGER DEFAULT 0,
    dribbles_completed    INTEGER DEFAULT 0,
    carries               INTEGER DEFAULT 0,
    yellow_cards          SMALLINT NOT NULL DEFAULT 0,
    red_cards             SMALLINT NOT NULL DEFAULT 0,
    aggregated_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (match_id, player_id)
);

COMMENT ON TABLE analytics.fact_player_match_stats IS 'OLAP fact. Grain: match_id × player_id (~2k rows)';

CREATE TABLE analytics.team_match_formation (
    match_id          INTEGER NOT NULL
        REFERENCES staging.matches (match_id),
    team_id           INTEGER NOT NULL
        REFERENCES staging.teams (team_id),
    from_minute       SMALLINT NOT NULL DEFAULT 0,
    to_minute         SMALLINT,
    formation_code    VARCHAR NOT NULL,
    source_event_type VARCHAR NOT NULL,
    PRIMARY KEY (match_id, team_id, from_minute)
);

COMMENT ON TABLE analytics.team_match_formation IS '경기×팀 포메이션 타임라인 (Starting XI / Tactical Shift)';

CREATE TABLE analytics.embedding_documents (
    doc_id     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_type   VARCHAR NOT NULL,
    ref_id     INTEGER NOT NULL,
    content    TEXT NOT NULL,
    embedding  vector(384),
    metadata   JSONB,
    created_at TIMESTAMPTZ
);

COMMENT ON TABLE analytics.embedding_documents IS 'RAG vector store (Phase 5). HNSW index deferred.';
