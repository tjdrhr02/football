# Football Tactical Intelligence Platform

StatsBomb Open Data → PostgreSQL staging → SQL analytics. Phase 1 proves the **data pipeline**: ingest ~235k events, aggregate to ~2k player-match facts (~119× compression).

## Quick start

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # set PGPASSWORD

football-init-db
football-pipeline --competition-id 43 --season-id 106
football-pipeline --counts-only
```

WC2022 defaults (`competition_id=43`, `season_id=106`) live in `src/football/config.py`. Change CLI flags to load another StatsBomb Open Data competition.

**Cloud (RDS):** the DB target is env-driven — point `.env`'s `PGHOST`/`PGUSER`/`PGPASSWORD` at the RDS endpoint and every `football-*` CLI runs against AWS unchanged. Provision/tear down the instance via `infra/terraform/` (see its README).

## Compression proof (psql)

```sql
SELECT 'staging.events', COUNT(*) FROM staging.events e
JOIN staging.matches m ON m.match_id = e.match_id
WHERE m.competition_id = 43 AND m.season_id = 106
UNION ALL
SELECT 'analytics.fact_player_match_stats', COUNT(*) FROM analytics.fact_player_match_stats f
JOIN staging.matches m ON m.match_id = f.match_id
WHERE m.competition_id = 43 AND m.season_id = 106;
-- Expected: 234,637 | 1,996
```

## CLI commands

| Command | Purpose |
|---------|---------|
| `football-pipeline` | Full ingest → aggregate (evaluator demo) |
| `football-ingest` | Staging only (`--table`, `--match-id`) |
| `football-aggregate` | Analytics ETL only |
| `football-init-db` | Apply `db/schema/*.sql` |
| `football-analysis` | Exploratory SQL → `docs/snapshots/` |
| `football-embed` | Build RAG docs (SQL→NL) + local embeddings → pgvector |
| `football-search` | Cosine similarity search (`--query`, `--doc-type`, `--top-k`) |
| `football-recommend` | Hybrid lineup rec: SQL → pgvector → Gemini (`--question`, `--dry-run`) |

Legacy wrappers: `run_pipeline.py`, `scripts/ingest.py`, etc.

## Repository layout

```
infra/terraform/    AWS RDS (free-tier, pgvector) as code — apply/destroy
db/schema/          DDL (staging + analytics + indexes)
sql/aggregate/      ETL SQL (fact, formation) — in src/football/sql/
src/football/       Package — ingest, aggregation, pipeline, rag, cli
scripts/            Dev tools (validate_erd, explain benchmark)
tests/              Unit tests (transformers, sql loader)
docs/performance/   EXPLAIN ANALYZE captures
docs/snapshots/     football-analysis JSON output
docs/decisions/     ERD memos (schema truth: db/erd.dbml)
explore/            PG-free StatsBomb API exploration
canvases/           Cursor Canvas (`analysis-story.canvas.tsx`)
```

Agent/implementation context: `AGENTS.md`.

## Development

```bash
make install    # editable install + dev deps
make validate   # ERD vs StatsBomb API (no PG)
make test       # pytest
make pipeline   # WC2022 full run
```

## Phase roadmap

| Day | Focus |
|-----|-------|
| 1~2 ✅ | Pipeline + indexes + EXPLAIN + 8 WC2022 analysis queries (Korea-focused) |
| 3 ✅ | AWS RDS PostgreSQL 16 (pgvector 0.8.0) via Terraform + local→RDS migration |
| 4 ✅ | RAG data prep: 56 docs (match reports + tactical patterns + Korea/Brazil player profiles), local bge-small-en-v1.5 (384-dim) embeddings, pgvector HNSW search |
| 5 ✅ | Hybrid lineup recommender: "Korea vs Brazil optimal lineup" — SQL facts → pgvector → Gemini (free tier), sourced rationale |
| 6~7 | Architecture diagram + README as "World Cup Tactical Analysis System" portfolio |

Data source: [StatsBomb Open Data](https://github.com/statsbomb/open-data) only.
