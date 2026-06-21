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

Legacy wrappers: `run_pipeline.py`, `scripts/ingest.py`, etc.

## Repository layout

```
db/schema/          DDL (staging + analytics + indexes)
sql/aggregate/      ETL SQL (fact, formation) — in src/football/sql/
src/football/       Package — ingest, aggregation, pipeline, cli
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
| 3 | AWS RDS PostgreSQL (pgvector enabled) + local→RDS migration |
| 4 | RAG data prep: embed WC match reports + tactical patterns + Korea player profiles |
| 5 | Hybrid lineup recommender: "Korea vs Brazil optimal lineup" (SQL→pgvector→LLM) |
| 6~7 | Architecture diagram + README as "World Cup Tactical Analysis System" portfolio |

Data source: [StatsBomb Open Data](https://github.com/statsbomb/open-data) only.
