-- staging (Silver) — StatsBomb source tables
-- Source: db/erd.dbml

CREATE TABLE staging.competitions (
    competition_id   INTEGER PRIMARY KEY,
    competition_name VARCHAR NOT NULL,
    country_name     VARCHAR,
    competition_gender VARCHAR,
    data_source      VARCHAR DEFAULT 'statsbomb_open',
    ingested_at      TIMESTAMPTZ
);

COMMENT ON TABLE staging.competitions IS '대회 마스터';

CREATE TABLE staging.seasons (
    competition_id INTEGER NOT NULL
        REFERENCES staging.competitions (competition_id),
    season_id      INTEGER NOT NULL,
    season_name    VARCHAR NOT NULL,
    PRIMARY KEY (competition_id, season_id)
);

COMMENT ON TABLE staging.seasons IS '시즌. PK=(competition_id, season_id)';

CREATE TABLE staging.teams (
    team_id      INTEGER PRIMARY KEY,
    team_name    VARCHAR NOT NULL,
    team_gender  VARCHAR,
    country_name VARCHAR,
    data_source  VARCHAR DEFAULT 'statsbomb_open',
    ingested_at  TIMESTAMPTZ
);

COMMENT ON TABLE staging.teams IS '32개 국가대표팀';

CREATE TABLE staging.players (
    player_id         INTEGER PRIMARY KEY,
    player_name       VARCHAR NOT NULL,
    player_nickname   VARCHAR,
    country_name      VARCHAR,
    data_source       VARCHAR DEFAULT 'statsbomb_open',
    ingested_at       TIMESTAMPTZ
);

COMMENT ON TABLE staging.players IS 'WC 출전 선수 마스터 (~800명)';

CREATE TABLE staging.matches (
    match_id          INTEGER PRIMARY KEY,
    competition_id    INTEGER NOT NULL
        REFERENCES staging.competitions (competition_id),
    season_id         INTEGER NOT NULL,
    match_date        DATE NOT NULL,
    kick_off          TIME,
    home_team_id      INTEGER NOT NULL
        REFERENCES staging.teams (team_id),
    away_team_id      INTEGER NOT NULL
        REFERENCES staging.teams (team_id),
    home_score        INTEGER,
    away_score        INTEGER,
    match_status      VARCHAR,
    competition_stage VARCHAR NOT NULL,
    match_week        INTEGER,
    stadium_name      VARCHAR,
    referee_name      VARCHAR,
    data_source       VARCHAR DEFAULT 'statsbomb_open',
    ingested_at       TIMESTAMPTZ,
    FOREIGN KEY (competition_id, season_id)
        REFERENCES staging.seasons (competition_id, season_id)
);

COMMENT ON TABLE staging.matches IS '64경기. 상대·일자·홈어웨이·대회 스테이지';

CREATE TABLE staging.events (
    event_id          UUID PRIMARY KEY,
    match_id          INTEGER NOT NULL
        REFERENCES staging.matches (match_id),
    index             INTEGER NOT NULL,
    period            SMALLINT NOT NULL,
    timestamp         VARCHAR,
    minute            SMALLINT,
    second            SMALLINT,
    type              VARCHAR NOT NULL,
    team_id           INTEGER
        REFERENCES staging.teams (team_id),
    player_id         INTEGER
        REFERENCES staging.players (player_id),
    location_x        DECIMAL(6, 2),
    location_y        DECIMAL(6, 2),
    duration          DECIMAL(8, 3),
    under_pressure    BOOLEAN,
    outcome           VARCHAR,
    shot_statsbomb_xg DECIMAL(6, 4),
    payload           JSONB NOT NULL DEFAULT '{}',
    ingested_at       TIMESTAMPTZ
);

COMMENT ON TABLE staging.events IS 'Raw events (~235k). ETL input; not scanned by analytics queries directly.';

CREATE TABLE staging.match_lineups (
    lineup_id     INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_id      INTEGER NOT NULL
        REFERENCES staging.matches (match_id),
    team_id       INTEGER NOT NULL
        REFERENCES staging.teams (team_id),
    player_id     INTEGER NOT NULL
        REFERENCES staging.players (player_id),
    jersey_number SMALLINT,
    is_starter    BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (match_id, team_id, player_id)
);

COMMENT ON TABLE staging.match_lineups IS '경기 스쿼드. 선발 여부 식별';

CREATE TABLE staging.match_lineup_positions (
    lineup_position_id   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lineup_id            INTEGER NOT NULL
        REFERENCES staging.match_lineups (lineup_id),
    position_name        VARCHAR NOT NULL,
    statsbomb_position_id INTEGER,
    from_period          SMALLINT,
    from_minute          SMALLINT,
    to_period            SMALLINT,
    to_minute            SMALLINT,
    start_reason         VARCHAR,
    end_reason           VARCHAR
);

COMMENT ON TABLE staging.match_lineup_positions IS '포지션·교체 시간 구간. minutes_played 집계에 사용';

CREATE TABLE staging.ingestion_runs (
    run_id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source            VARCHAR NOT NULL DEFAULT 'statsbomb_open',
    competition_id    INTEGER NOT NULL,
    season_id         INTEGER NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ,
    status            VARCHAR NOT NULL,
    matches_processed INTEGER DEFAULT 0,
    events_processed  INTEGER DEFAULT 0,
    error_message     TEXT
);

COMMENT ON TABLE staging.ingestion_runs IS '배치 멱등·재처리 추적';
