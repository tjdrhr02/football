-- Football WC2022 — schema bootstrap
-- Source: db/erd.dbml
-- Indexes: PK/FK only (performance indexes → docs/performance/ later)

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA staging IS 'Silver layer — StatsBomb raw source';
COMMENT ON SCHEMA analytics IS 'Gold layer — aggregates and AI/RAG';
