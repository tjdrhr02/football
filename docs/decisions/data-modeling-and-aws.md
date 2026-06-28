# 데이터 모델링 & AWS 인프라 정리

> WC2022 축구 전술 분석 플랫폼 — 설계 결정 요약  
> 대상 독자: 처음 보는 사람도 이해할 수 있도록 작성

---

## 목차

1. [왜 모델링이 필요했나](#1-왜-모델링이-필요했나)
2. [전체 구조](#2-전체-구조)
3. [Staging (Silver) — 창고](#3-staging-silver--창고)
4. [Analytics (Gold) — 매장 진열](#4-analytics-gold--매장-진열)
5. [Embedding Documents — AI 문서](#5-embedding-documents--ai-문서)
6. [지표 정의](#6-지표-정의)
7. [인덱스 — 쿼리 성능](#7-인덱스--쿼리-성능)
8. [AWS 인프라](#8-aws-인프라)

---

## 1. 왜 모델링이 필요했나

StatsBomb에서 받은 WC2022 원본 데이터는 이벤트 단위입니다.

> "2022년 12월 5일, 브라질 vs 한국, 4분 38초, 빈첸시우가 드리블 시도, 왼발, 위치 X:61 Y:42, 압박 있음, 결과: 성공..."

경기 64개, 이런 이벤트가 **23만 5천 건**입니다.

이걸 그냥 쌓아만 두면 "손흥민이 이번 대회에서 패스 성공률이 얼마야?" 같은 질문에 매번 23만 건을 전부 뒤져야 합니다. **"어떻게 저장할지"를 설계한 것**이 데이터 모델링입니다.

---

## 2. 전체 구조

편의점 재고에 비유하면 이렇습니다.

```
StatsBomb API
      ↓
[ 창고 — staging ]        원재료 그대로 보관 (~235k 이벤트)
      ↓  ETL 가공
[ 매장 진열 — analytics ] 손님이 바로 쓸 수 있게 정리 (~2k 팩트)
      ↓  자연어화
[ 상품 설명서 — embedding_documents ]  AI가 읽는 문서 (56건)
```

| 계층 | 역할 | 규모 | 언제 쓰나 |
|------|------|------|-----------|
| staging | 원천 보존 | events ~235k | ETL 재실행, 이벤트급 탐색 |
| analytics | 분석 grain | fact ~2k | DA/AI 질의 진입점 |
| embedding_documents | RAG 벡터 저장소 | 56 docs | 라인업 추천 유사 검색 |

---

## 3. Staging (Silver) — 창고

원본을 버리지 않고 **8개 테이블**로 보존합니다.

| 테이블 | 비유 | 내용 |
|--------|------|------|
| competitions | 대회 목록 | FIFA WC, 프리미어리그... |
| seasons | 연도 | 2022, 2023... |
| teams | 팀 명단 | 브라질, 한국, 포르투갈... |
| players | 선수 명단 | 손흥민, 메시... |
| matches | 경기 기록 | 일자, 스코어, 홈/어웨이, 스테이지 |
| **events** | ★ 이벤트 원본 | 패스, 슈팅, 드리블... 23만5천 건 |
| match_lineups | 출전 명단 | 선발/교체 여부 |
| match_lineup_positions | 포지션 구간 | 0분~45분 LB, 45분~90분 LM |

### events 설계 — 핵심 결정

이벤트 타입이 30가지가 넘는데, 타입마다 다른 속성이 있습니다.

| 방법 | 내용 | 문제 |
|------|------|------|
| ❌ A | 타입별 컬럼 94개 전부 만들기 | 대부분의 행이 대부분의 컬럼에서 빈칸 |
| ✅ B | 공통 속성만 컬럼 + 나머지는 JSONB `payload` | 스키마 깔끔, 원천 손실 없음 |

**B를 선택한 이유:**

- 공통으로 쓰는 것(type, minute, player, outcome, xG)은 컬럼으로 → 집계 SQL이 읽기 쉬움
- 타입별 특수 속성(드리블 방향, 파울 카드 색상 등)은 JSONB 한 칸에 → 스키마 폭발 방지
- ETL에서 필요할 때 `payload->>'duel_type'` 등으로 꺼냄

```sql
-- 컬럼화된 것 (집계에서 바로 사용)
type, minute, player_id, outcome, shot_statsbomb_xg

-- JSONB payload (ETL에서 필요 시 파싱)
payload->>'duel_type'           -- 태클 판별
payload->>'pass_goal_assist'    -- 어시스트 판별
payload->'tactics'->>'formation' -- 포메이션 파싱
```

### match_lineup_positions — 왜 lineups를 2개로 쪼갰나

교체·포지션 변경이 **구간(interval)** 으로 기록되기 때문입니다.

```
손흥민 | 브라질전 | 0분 ~ 93분  | Left Midfield    (선발)
홍철   | 브라질전 | 45분 ~ 93분 | Left Back         (교체)
```

`minutes_played`는 이 구간의 합으로 계산하고, `to_minute IS NULL`이면 경기 MAX(minute)까지로 처리합니다.

### ingestion_runs — 멱등성 추적

시즌 재적재, 단일 경기 재실행, 실패 복구 시 "언제 무엇을 넣었는지" 기록하는 운영 테이블입니다.

---

## 4. Analytics (Gold) — 매장 진열

### fact_player_match_stats ★ 핵심

```
Grain (단위): 선수 1명 × 경기 1개 = 행 1개

손흥민 | 브라질전 | LW | 93분 | 패스 22/34 | 태클 0 | 압박 15 | 0골 0도움
메시   | 결승전   | CF | 120분| 패스 ...   | ...    | ...     | 2골 1도움
```

| 항목 | 값 |
|------|-----|
| 행 수 | ~2,000행 |
| 압축 비율 | events 235k → fact 2k (**119배**) |
| PK | `(match_id, player_id)` |

**왜 이 grain(단위)인가?**  
DA 질문의 90%가 이 형태입니다.

- "손흥민이 이 대회에서 몇 골?" → `WHERE player_id=... SUM(goals)`
- "한국 수비진 압박 횟수?" → `WHERE team_id=791 SUM(pressures)`
- "승팀 패스 성공률 vs 패팀?" → `GROUP BY result`

**dim 테이블(dim_player, dim_team)을 안 만든 이유:**

- fact가 고작 2천 행 → Kimball 스타 스키마는 과설계
- 선수 이름·팀 이름은 `staging.players`, `staging.teams`에 이미 있음
- JOIN 한 번이면 충분 → 별도 dim 유지 비용 낭비

### team_match_formation — 포메이션은 왜 별도 테이블인가

포메이션을 fact에 컬럼 하나로 붙이면:

```
손흥민 | 브라질전 | formation=442 ← 전반만 442였는데?
```

브라질전에서 한국은 **전반 4-4-2 → 후반 4-1-4-1**로 바뀌었습니다.  
경기 중간에 바뀌는 값은 컬럼 하나로 표현할 수 없습니다.

그래서 **타임라인 테이블**로 분리:

```
한국  | 브라질전 | 0분  ~ 45분  | 4-4-2     (Starting XI)
한국  | 브라질전 | 45분 ~ 종료  | 4-1-4-1   (Tactical Shift)
브라질 | 브라질전 | 0분  ~ 80분  | 4-2-3-1   (Starting XI)
브라질 | 브라질전 | 80분 ~ 종료  | 4-4-1-1   (Tactical Shift)
```

- PK: `(match_id, team_id, from_minute)` → "60분에 상대 포메이션이 뭐였나?" 정확히 조회 가능
- fact와 FK 없이 JOIN → 포메이션 변경 시점 모호함 방지

---

## 5. Embedding Documents — AI 문서

fact는 숫자, LLM(Gemini)은 문장으로 이야기합니다. 그 사이를 잇는 벡터 저장소입니다.

| doc_type | ref_id | 예시 내용 |
|----------|--------|----------|
| match_report | match_id | "한국은 브라질전에서 0.34 xG를 기록했고, 압박 수비에 시달렸다..." |
| tactical_pattern | team_id | "브라질은 4-2-3-1로 측면 압박을 강하게 걸었다..." |
| player_profile | player_id | "손흥민: 4경기 0골 1도움, xG 0.45, 패스 성공률 68.9%..." |

이 문장들을 **bge-small-en-v1.5** (로컬 AI 모델, 무료)로 벡터(384차원)로 변환해 저장합니다.  
질문이 들어오면 가장 비슷한 문장들을 꺼내서 Gemini에 컨텍스트로 주입합니다.

**AI 추천 3단계 흐름:**

```
[1/3] SQL  →  fact + formation에서 실측 수치 조회
[2/3] 벡터  →  embedding_documents에서 유사 사례 검색
[3/3] Gemini  →  위 컨텍스트만 근거로 포메이션·11인 답변 생성
                 (순수 LLM 단독 추천 금지)
```

---

## 6. 지표 정의

설계에서 놓치기 쉬운 부분: **지표 정의를 ETL SQL에 명시**합니다.  
정의가 코드에 없으면 사람마다 다르게 집계합니다.

| 지표 | 정의 | 근거 |
|------|------|------|
| 패스 성공 | `type='Pass' AND outcome IS NULL` | StatsBomb 규칙: 성공 시 outcome 없음 |
| 태클 | `type='Duel' AND payload->>'duel_type'='Tackle'` | Duel에 태클 포함 |
| 어시스트 | `type='Pass' AND payload->>'pass_goal_assist' IS NOT NULL` | JSONB 파싱 |
| 압박 | `under_pressure = TRUE` (NULL은 압박 없음) | StatsBomb 규칙 |
| 출전 시간 | lineup_positions 구간 합, to_minute NULL → MAX(minute) | 교체/퇴장 정확 반영 |

---

## 7. 인덱스 — 쿼리 성능

인덱스는 **"어떤 질문을 자주 하느냐"에서 역설계**했습니다.

```sql
-- ETL: 경기별 선수 이벤트 집계
idx_events_match_type_player  ON events (match_id, type, player_id)

-- 분석: 선수/팀별 경기 fact 조회
idx_fpms_player_match         ON fact (player_id, match_id)
idx_fpms_team_match           ON fact (team_id, match_id)

-- covering index: 자주 쓰는 컬럼 묶어 Index Only Scan
idx_fpms_cover                ON fact (player_id, match_id)
                               INCLUDE (xg, passes_attempted, passes_completed, ...)

-- 포메이션 타임라인 조회
idx_tmf_timeline              ON team_match_formation (match_id, team_id, from_minute)
```

**성능 개선 결과:**

| 쿼리 | 인덱스 전 | 인덱스 후 | 개선 |
|------|----------|----------|------|
| ETL 이벤트 집계 (경기별 패스/슈팅) | Seq Scan 130.5ms | Index Scan 0.9ms | **144배** |
| 한국 경기별 수비 집계 | Seq Scan 0.24ms | Index Scan 0.025ms | 9.7배 |
| 선수 스탯 covering 조회 | Index Scan 0.057ms | Index Only Scan 0.024ms | 2.4배 |
| 포메이션 타임라인 | Seq Scan 0.026ms | Seq Scan 0.012ms | 2.2배 |

---

## 8. AWS 인프라

### 사용 서비스: Amazon RDS 하나

**Amazon RDS for PostgreSQL 16** — 서울 리전 (`ap-northeast-2`)

```
인스턴스 : db.t4g.micro
스토리지 : 20GB gp2
PostgreSQL: 16.9 (pgvector 0.8.0 포함)
```

### 왜 RDS를 선택했나

**① pgvector가 필요했다**

RAG(벡터 검색)를 구현하려면 임베딩 값을 저장하고 유사도 검색을 해야 합니다.  
RDS PostgreSQL 16은 `pgvector`를 기본 지원합니다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;  -- RDS에서 바로 가능
CREATE INDEX ON embedding_documents USING hnsw (embedding vector_cosine_ops);
```

**② 무료 티어 — 비용 0원**

`db.t4g.micro`는 프리티어로 월 750시간 무료입니다.  
사실상 한 달 내내 켜 놔도 무료 범위 안입니다.

비용 방어를 위해 Terraform에 명시한 설정:

```hcl
max_allocated_storage        = 0     # 스토리지 자동 확장 차단
multi_az                     = false # Multi-AZ 미사용 (유료)
performance_insights_enabled = false # CloudWatch 과금 방지
monitoring_interval          = 0     # Enhanced Monitoring 미사용
```

**③ 포트폴리오 증명**

"로컬에서만 돌아가는 파이프라인"이 아니라 **"클라우드 DB에 연결된 파이프라인"** 을 보여줄 수 있습니다.  
`.env`의 `PGHOST`만 RDS 엔드포인트로 바꾸면 모든 CLI가 그대로 동작합니다.

```bash
# 로컬 → PGHOST=localhost
# RDS  → PGHOST=football-rds.cfaoymgg6xjz.ap-northeast-2.rds.amazonaws.com
# 코드 변경 없이 동일하게 동작
football-recommend
football-pipeline --competition-id 43 --season-id 106
```

### RDS와 함께 생성된 AWS 리소스

RDS 인스턴스 하나를 위해 따라오는 부속 리소스입니다.

| AWS 리소스 | 역할 |
|-----------|------|
| VPC (기본 VPC 재사용) | RDS가 들어갈 네트워크. 새로 만들지 않고 계정 기본값 사용 |
| 보안 그룹 (Security Group) | "내 IP에서만 5432 포트 허용" 방화벽 |
| DB 서브넷 그룹 | RDS가 배치될 서브넷 지정 |

> **보안 그룹 주의:** IP가 바뀔 때마다 `terraform apply -var="my_ip=$(curl -s ifconfig.me)/32"` 로 갱신해야 합니다.

### 왜 다른 서비스는 안 썼나

| 서비스 | 안 쓴 이유 |
|--------|-----------|
| EC2 | 파이프라인이 로컬 실행 → 별도 서버 불필요 |
| S3 | Raw 파일 저장 불필요 (StatsBomb 직접 API 호출) |
| Lambda / Airflow | 스케줄 배치 없음, 데모 1회성 실행 |
| RDS Proxy | 단일 CLI 연결 → 커넥션 풀링 불필요 |

> Phase 2 계획에는 S3 + Airflow가 포함됩니다. 현재는 파이프라인 증명이 목적이라 RDS 하나로 충분합니다.

---

## 설계 철학 요약

| 원칙 | 적용 |
|------|------|
| 원본은 staging에 보존 | events 전체를 payload JSONB로 손실 없이 |
| 질문 grain에 맞게 압축 | 235k → 2k (선수×경기 단위) |
| 작은 데이터엔 simple schema | dim 없이 staging 직접 JOIN |
| 시간이 있는 개념은 타임라인으로 | team_match_formation |
| 이벤트 이질성은 컬럼 + JSONB hybrid | events 설계 |
| AI layer는 복제가 아닌 자연어 보조 | embedding_documents |
| 클라우드는 꼭 필요한 것만 | RDS 하나 (pgvector 목적) |
