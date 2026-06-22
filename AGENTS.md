# Football Tactical Intelligence Platform — Agent Context

> Cursor 에이전트 **시스템 프롬프트**. 구현 전 필독. 불명확한 결정은 사용자에게 확인.  
> ERD: `db/erd.dbml` | 검증: `scripts/validate_erd.py`

---

## 0. 변경 검증 (최우선)

코드·스키마·ETL 수정 후 작업 종료 전 서브 에이전트 검증. **문서만 수정 시 제외.**

| 서브 에이전트 | 역할 | 언제 |
|---------------|------|------|
| **`bugbot`** | Python·SQL·ETL 리뷰 (§5, 멱등성) | `.py`, `db/schema/`, ingest·aggregation **코드 변경 시** |
| **`shell`** | `validate_erd.py` + §7 검증 SQL | DDL, ETL·스키마·적재 경로 변경 시 |

스키마·ETL → `bugbot` + `shell` **병렬**. Python만 → `bugbot`만. Phase 1은 `security-review`/`generalPurpose` **미사용**.

**순서**: 구현 → 검증 → 이슈 수정·재검증 → 보고 (bugbot: Severity\|Location\|Finding, shell: 기대값 vs 실측)

**bugbot 호출**: `subagent_type: bugbot`, `readonly: true`, `Diff: uncommitted changes`,  
`Custom Instructions: AGENTS.md §5 ETL·Phase 1 범위`

**shell 호출**: `.venv/bin/python scripts/validate_erd.py` + §7 SQL (matches 64, events 234637, fact 1996, formation ~218)

| 사용자 요청 | 동작 |
|-------------|------|
| "리뷰" / "버그 찾아줘" | `bugbot` |
| "검증" / "ERD 확인" | `shell` |
| "변경 확인" (스키마·ETL) | `bugbot` + `shell` |

---

## 1. 프로젝트 정체성

**AI 기반 축구 전술 의사결정 플랫폼** (포트폴리오). 장기: 수집→분석→AI. **Phase 1 = 파이프라인 증명.**

```
StatsBomb API → staging (Silver, events ~235k) → analytics (Gold, fact ~2k) → (Phase 5) SQL+RAG+LLM
```

| 역량 | Phase 1 | 이후 |
|------|---------|------|
| DE | API→PG staging, 멱등 적재, `ingestion_runs` | S3, Airflow (Ph.2) |
| DA | fact 집계 ~119배 축소, EXPLAIN ANALYZE | — |
| AI | — | SQL→pgvector→LLM 라인업 (Ph.5) |

**시드**: WC2022 (`competition_id=43`, `season_id=106`). 우리 팀 Korea `team_id=791`.  
**설정**: `src/football/config.py` — `DB_CONFIG`, `COMPETITION_ID`, `SEASON_ID`, `KOREA_TEAM_ID`. env: `PGHOST` 등 (`.env.example`).

### Phase 1 평가자 데모

```bash
football-pipeline --competition-id 43 --season-id 106
# 또는: .venv/bin/python run_pipeline.py ...
# 다른 대회: competition-id/season-id만 변경. --counts-only 로 축소율 즉시 확인
```

psql 압축 증명 (시즌 scope):

```sql
SELECT 'staging.events', COUNT(*) FROM staging.events e
JOIN staging.matches m ON m.match_id = e.match_id
WHERE m.competition_id = 43 AND m.season_id = 106
UNION ALL
SELECT 'analytics.fact_player_match_stats', COUNT(*) FROM analytics.fact_player_match_stats f
JOIN staging.matches m ON m.match_id = f.match_id
WHERE m.competition_id = 43 AND m.season_id = 106;
-- WC2022: 234,637 | 1,996
```

개발·디버그: `football-ingest` / `scripts/ingest.py` (`--table`, `--match-id`), `football-aggregate` / `scripts/run_aggregation.py`.

### 최종 목표 — AI 라인업 추천 (Phase 5)

**한 줄**: "데이터 분석과 AI가 어떻게 결합되는가" — 감독 질의→근거 달린 추천까지 **코드로 보여줌**.

| 항목 | 값 |
|------|-----|
| 상대 | Brazil `781`, head-to-head `match_id=3869253` (16강 0-4) |
| 질의 예 | "브라질 4-3-3·고압박 대응, 가용 전원 출전, 최적 라인업·전술" |

**3단계 (순수 LLM 단독 금지)**

1. **SQL** — `query_korea_vs_brazil_stats()`: fact + formation + staging JOIN (`3869253` 실측)
2. **pgvector** — `search_similar_tactical_pattern()`: `embedding_documents` top-k  
   임베딩 대상: WC2022 경기 리포트 + 상대팀 전술 패턴 + 한국 선수 프로파일  
   핵심 소재: Q5 한국 경기 상대별 수비 기여도 쿼리 결과를 자연어로 변환해 임베딩
3. **LLM** — `sql_context + vector_context + user_input` → 포메이션·11인·**출처 명시 근거**·주의사항

출력: 추천 포메이션(예 3-5-2), 선발 11인, ①포메이션 이유 ②선수 WC2022 기록 ③유사 사례 — 각 항목 데이터 출처 필수.  
완료: Step 1→2→3 CLI 로그, `3869253` fact와 일치, 근거 없는 경로 없음.

> LLM 단독 아님. SQL 선계산 → 유사 사례 검색 → 컨텍스트 주입.

### 레포지터리 구조

```
football/
├── README.md, Makefile, pyproject.toml, run_pipeline.py
├── db/erd.dbml, db/schema/          DDL (staging, analytics, indexes)
├── src/football/
│   ├── cli/                         football-* entry points
│   ├── ingest/, aggregation/, pipeline/, db/
│   └── sql/aggregate/               ETL SQL (fact, formation)
├── scripts/                         validate_erd, run_explain_benchmark (+ wrappers)
├── tests/
├── docs/performance/                EXPLAIN captures
├── docs/snapshots/                  football-analysis JSON
├── docs/decisions/                  design memos (ERD: db/erd.dbml)
├── explore/statsbomb_explore.py     API 탐색 (PG 불필요)
└── canvases/analysis-story.canvas.tsx
```

| CLI | 역할 |
|-----|------|
| `football-pipeline` | ingest → aggregate (평가자 데모) |
| `football-ingest` | staging (`--table`, `--match-id`) |
| `football-aggregate` | analytics ETL |
| `football-init-db` | DDL 적용 |
| `football-analysis` | 탐색 SQL → `docs/snapshots/analysis_results.json` |

로컬: `pip install -e ".[dev]"` 후 `make validate` / `make test`.

---

## 2. 데이터 레이어

| | staging (Silver) | analytics (Gold) |
|---|------------------|------------------|
| 역할 | StatsBomb 원천 보존 | 집계·분석·AI SQL 진입점 |
| 규모 | events ~235k | fact ~2k `(match_id, player_id)` |
| 핵심 테이블 | 8 (competitions…ingestion_runs) | fact_player_match_stats ★, team_match_formation, embedding_documents (Ph.5) |

**제거 확정**: `oltp.*`, `analytics.dim_*`, fact→formation FK (→ `team_match_formation` 타임라인).  
**범위 제외**: StatsBomb 외 소스, 합성 데이터, 웹 UI·인증, 유료 API.

ERD 11테이블 상세: `db/erd.dbml`. FK는 staging ID 직접 참조 (dim 없음).

---

## 3. 진행 상황

### WC2022 실측 (검증 기준)

| 항목 | 값 |
|------|-----|
| matches / events / players | 64 / 234,637 / 829 |
| fact / formation | 1,996 / 218 |
| Korea fact / 경기 | 60 / 3857287, 3857299, 3857262, **3869253** |

### 체크리스트

```
[✅] DDL + init_db, config/connection, ingest, aggregation, run_pipeline, analysis CLI
[✅] db/schema/03_indexes.sql + docs/performance/ EXPLAIN
[✅] Day 3: AWS RDS PG16 (pgvector 0.8.0) Terraform + 로컬→RDS 마이그레이션
[✅] Day 4: RAG 문서 56개(match_report/tactical_pattern/player_profile) + 로컬 bge-small(384) 임베딩 + HNSW
[ ] Day 5: 하이브리드 라인업 추천 (§1)
```

**파이프라인**: statsbombpy → Python 정제 → staging 8테이블 → §4 ETL → analytics fact+formation.  
**멱등**: 시즌 재적재 DELETE+INSERT; `--match-id` 단일 경기; `ingestion_runs` 추적; 집계는 match scope DELETE 후 INSERT.

**ingest 순서**: competitions→seasons→teams→players→matches→(경기별) events, lineups.  
**정제 요약**: `pass_outcome`/`shot_outcome`→`outcome`; sparse→`payload` JSONB; `location`→x/y; lineup `'64:10'`→분 정수.

| Day / Phase | 내용 |
|-------------|------|
| Day 1~2 ✅ | WC2022 파이프라인, 분석 쿼리 8개 (Q5 한국 수비기여도, E3 한국 xG 밸런스) |
| Day 3 ✅ | AWS RDS PG16 (pgvector 0.8.0) Terraform 프로비저닝, 로컬→RDS pg_dump/restore. `infra/terraform/`, DB는 `.env` PGHOST로 전환 |
| Day 4 ✅ | RAG: SQL→NL 문서 56개 + 로컬 bge-small-en-v1.5(384, 비용0·오프라인) 임베딩 + pgvector HNSW. `football-embed`/`football-search`, `src/football/rag/` |
| Day 5 | 하이브리드 라인업 추천 구현: "한국 vs 브라질 최적 라인업" 데모 (SQL→pgvector→LLM 3단계) |
| Day 6~7 | 아키텍처 다이어그램, README "월드컵 전술 분석 시스템" 스토리 정리, 포트폴리오 마무리 |

---

## 4. ETL 집계 규칙

> sparse → `payload`. passes_completed = Pass **`outcome IS NULL`**. tackles = Duel + `duel_type='Tackle'`.

| fact 컬럼 | 규칙 |
|-----------|------|
| grain | `player_id IS NOT NULL` DISTINCT `(match_id, player_id)` → 1,996 |
| passes | attempted=Pass COUNT; completed=outcome NULL |
| shots/goals/on_target | Shot; outcome Goal; Saved\|Goal |
| pressures/tackles/interceptions/blocks/carries | type COUNT (tackles= Duel+payload) |
| dribbles | attempted=COUNT; completed=outcome NULL |
| assists | Pass + `payload->>'pass_goal_assist' IS NOT NULL` |
| xg / xa | shot_statsbomb_xg SUM / **0 고정** |
| cards | Foul/Bad Behaviour payload card |
| minutes | lineup_positions 구간 합; to_minute NULL→경기 MAX(minute) |
| is_starter/position | lineups.is_starter; 최장 position_name |
| pass_completion_rate | completed/attempted (attempted>0) |
| progressive_passes | NULL |

**team_match_formation**: Starting XI/Tactical Shift → `payload.tactics.formation`; 연속 동일 스킵; 동일 분 `DISTINCT ON … ORDER BY index DESC`; `to_minute=LEAD(from_minute)`.

**3869253 검증**: Korea 0'442→45'4141 | Brazil 0'4231→80'4411

**events 주의**: `under_pressure` TRUE만 명시, NULL=무압박.

---

## 5. 인덱스 (Step 5)

```sql
CREATE INDEX idx_fpms_player_match ON analytics.fact_player_match_stats (player_id, match_id);
CREATE INDEX idx_fpms_team_match   ON analytics.fact_player_match_stats (team_id, match_id);
CREATE INDEX idx_fpms_cover ON analytics.fact_player_match_stats (player_id, match_id)
  INCLUDE (xg, passes_attempted, passes_completed, pass_completion_rate, minutes_played);
CREATE INDEX idx_events_match_type_player ON staging.events (match_id, type, player_id);
CREATE INDEX idx_tmf_timeline ON analytics.team_match_formation (match_id, team_id, from_minute);
```

`EXPLAIN (ANALYZE, BUFFERS)` 전후 → `docs/performance/`

---

## 6. 에이전트 지침

**우선순위**: ~~파이프라인·인덱스~~ ✅ → **Phase 5 AI**.

**하지 말 것**: oltp/dim_* 재도입, events 94컬럼 wide, 합성 데이터, AI를 ETL 전에, 순수 LLM 추천.

### 검증 SQL (§7)

```sql
-- 압축 (§1 UNION과 동일)
SELECT COUNT(*) FROM staging.matches WHERE competition_id=43 AND season_id=106;  -- 64
SELECT COUNT(*) FROM staging.events;       -- 234,637
SELECT COUNT(*) FROM staging.players;      -- 829
SELECT COUNT(*) FROM analytics.fact_player_match_stats;   -- 1,996
SELECT COUNT(*) FROM analytics.team_match_formation;      -- 218
SELECT COUNT(*) FROM analytics.fact_player_match_stats WHERE team_id=791;  -- 60

SELECT team_id, from_minute, to_minute, formation_code
FROM analytics.team_match_formation WHERE match_id=3869253 ORDER BY team_id, from_minute;
```

탐색: `football-analysis` 또는 `scripts/analysis.py` → `docs/snapshots/analysis_results.json`

---

## 7. 결정 로그 (요약)

| 날짜 | 결정 |
|------|------|
| 2026-06-14 | WC2022 시드, StatsBomb only, Korea 791 |
| 2026-06-14 | ERD 11테이블, oltp·dim_* 제거, team_match_formation |
| 2026-06-14 | passes_completed=outcome NULL, tackles=Duel+Tackle |
| 2026-06-14 | SQL+RAG+LLM, 변경 후 bugbot/shell 검증 |
| 2026-06-14 | run_pipeline 통합 CLI, §1 AI 라인업 최종 목표 (3869253) |
| 2026-06-14 | 레포 구조: cli/, sql/aggregate, tests, CI, docs/snapshots |

**참고**: StatsBomb https://github.com/statsbomb/open-data | 결승 `3869685` | 16강 한국vs브라질 `3869253`
