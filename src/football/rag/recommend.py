"""Day 5 — hybrid lineup recommendation: SQL facts + pgvector context + Gemini.

Three grounded stages (no pure-LLM path):
  1. matchup_stats()       — real WC2022 numbers (Korea squad, opponent profile, head-to-head 3869253)
  2. retrieve_context()    — pgvector similarity hits (reuses rag.embedder.search_similar)
  3. generate()            — Gemini composes formation + XI + sourced rationale

LLM provider is Google Gemini (free tier) — set GEMINI_API_KEY. Output defaults to Korean.
"""
from __future__ import annotations

from psycopg2.extensions import connection as PGConnection

from football.config import (
    BRAZIL_TEAM_ID,
    COMPETITION_ID,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    KOREA_TEAM_ID,
    SEASON_ID,
)
from football.rag import documents as docs
from football.rag.embedder import search_similar

HEAD_TO_HEAD_MATCH_ID = 3869253  # Korea vs Brazil, Round of 16

DEFAULT_QUESTION = (
    "한국이 16강에서 만난 브라질을 다시 상대한다고 할 때, 가용 선수 풀과 직전 맞대결 "
    "데이터를 근거로 최적의 포메이션과 선발 11인을 추천해줘."
)

SYSTEM_GUIDANCE = (
    "당신은 축구 전술 분석가입니다. 아래에 제공된 SQL 실측 데이터와 검색된 유사 사례에만 "
    "근거해 답하세요. 데이터에 없는 선수나 수치를 지어내지 마세요. "
    "한국어로, 다음을 포함해 답하세요: (1) 추천 포메이션과 그 이유, (2) 선발 11인(포지션별), "
    "(3) 각 핵심 선수의 WC2022 기록 근거, (4) 직전 브라질전(match_id=3869253)에서 얻은 교훈. "
    "각 주장 뒤에 근거 출처를 [출처: ...] 형식으로 표기하세요."
)


# --------------------------------------------------------------------------- #
# Stage 1 — SQL facts
# --------------------------------------------------------------------------- #
def matchup_stats(
    conn: PGConnection,
    opponent_id: int = BRAZIL_TEAM_ID,
    match_id: int = HEAD_TO_HEAD_MATCH_ID,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
) -> dict:
    """Real WC2022 numbers grounding the recommendation."""
    with conn.cursor() as cur:
        korea_squad = docs.player_profiles(cur, competition_id, season_id, [KOREA_TEAM_ID])
        opp_aggs = docs.team_aggregates(cur, competition_id, season_id, [opponent_id])
        opp_agg = opp_aggs[0] if opp_aggs else None
        formations = docs.team_formations(cur, competition_id, season_id, [opponent_id])
        opp_formations = formations.get(opponent_id, [])

        # head-to-head match meta + formations + Korea XI
        cur.execute(
            """
            SELECT m.match_date, m.competition_stage,
                   ht.team_name AS home, at.team_name AS away,
                   m.home_score, m.away_score, m.home_team_id, m.away_team_id
            FROM staging.matches m
            JOIN staging.teams ht ON ht.team_id = m.home_team_id
            JOIN staging.teams at ON at.team_id = m.away_team_id
            WHERE m.match_id = %s
            """,
            (match_id,),
        )
        row = cur.fetchone()
        meta = None
        if row:
            cols = [d[0] for d in cur.description]
            meta = dict(zip(cols, row))

        cur.execute(
            """
            SELECT tmf.team_id, t.team_name, tmf.from_minute, tmf.to_minute, tmf.formation_code
            FROM analytics.team_match_formation tmf
            JOIN staging.teams t ON t.team_id = tmf.team_id
            WHERE tmf.match_id = %s
            ORDER BY tmf.team_id, tmf.from_minute
            """,
            (match_id,),
        )
        h2h_formations = [
            dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()
        ]

        cur.execute(
            """
            SELECT p.player_name, f.position_played, f.minutes_played, f.is_starter,
                   f.passes_completed, f.passes_attempted,
                   f.tackles, f.interceptions, f.pressures, f.goals, f.assists
            FROM analytics.fact_player_match_stats f
            JOIN staging.players p ON p.player_id = f.player_id
            WHERE f.match_id = %s AND f.team_id = %s
            ORDER BY f.is_starter DESC, f.minutes_played DESC
            """,
            (match_id, KOREA_TEAM_ID),
        )
        korea_h2h = [
            dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()
        ]

    return {
        "opponent_id": opponent_id,
        "opponent_name": opp_agg["team_name"] if opp_agg else str(opponent_id),
        "match_id": match_id,
        "korea_squad": korea_squad,
        "opponent_agg": opp_agg,
        "opponent_formations": opp_formations,
        "h2h_meta": meta,
        "h2h_formations": h2h_formations,
        "korea_h2h": korea_h2h,
    }


def format_sql_context(stats: dict) -> str:
    opp = stats["opponent_name"]
    lines: list[str] = []
    lines.append(f"## 상대팀 프로파일 — {opp} [출처: analytics.team_match_formation, fact_player_match_stats]")
    a = stats["opponent_agg"]
    if a:
        lines.append(
            f"{opp}: {a['matches']}경기, 포메이션 {', '.join(stats['opponent_formations']) or 'n/a'}, "
            f"{a['goals']}골 {a['xg']}xG, 수비액션(태클 {a['tackles']}/인터셉트 {a['interceptions']}/"
            f"압박 {a['pressures']}/블록 {a['blocks']}), 패스성공 {a['passes_completed']}/{a['passes_attempted']}."
        )

    m = stats["h2h_meta"]
    if m:
        lines.append(f"\n## 직전 맞대결 (match_id={stats['match_id']}) [출처: staging.matches, team_match_formation]")
        lines.append(
            f"{m['competition_stage']} {m['match_date']}: {m['home']} {m['home_score']}-{m['away_score']} {m['away']}."
        )
        for f in stats["h2h_formations"]:
            rng = f"{f['from_minute']}'~" + (f"{f['to_minute']}'" if f["to_minute"] is not None else "종료")
            lines.append(f"  - {f['team_name']} {f['formation_code']} ({rng})")

    if stats["korea_h2h"]:
        lines.append(f"\n## 그 경기 한국 출전 선수 [출처: fact_player_match_stats match_id={stats['match_id']}]")
        for p in stats["korea_h2h"]:
            tag = "선발" if p["is_starter"] else "교체"
            lines.append(
                f"  - {p['player_name']} ({p['position_played'] or '?'}, {tag}, {p['minutes_played']}분): "
                f"패스 {p['passes_completed']}/{p['passes_attempted']}, 태클 {p['tackles']}, "
                f"인터셉트 {p['interceptions']}, 압박 {p['pressures']}, {p['goals']}골 {p['assists']}도움"
            )

    lines.append("\n## 한국 가용 선수 풀 (WC2022 시즌 집계) [출처: analytics.fact_player_match_stats team_id=791]")
    for p in stats["korea_squad"]:
        lines.append(
            f"  - {p['player_name']} ({p['position'] or '?'}): {p['matches']}경기 {p['minutes']}분, "
            f"{p['goals']}골 {p['assists']}도움 {p['xg']}xG, 패스 {p['passes_completed']}/{p['passes_attempted']}, "
            f"태클 {p['tackles']}/인터셉트 {p['interceptions']}/압박 {p['pressures']}/블록 {p['blocks']}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Stage 2 — vector context
# --------------------------------------------------------------------------- #
def retrieve_context(
    conn: PGConnection, question: str, opponent_name: str, top_k: int = 5
) -> tuple[list[dict], str]:
    tactical = search_similar(
        conn, f"{opponent_name} pressing tactics formation against Korea",
        top_k=3, doc_type="tactical_pattern",
    )
    players = search_similar(conn, question, top_k=top_k, doc_type="player_profile")
    hits = tactical + players
    lines = ["## 벡터 유사 검색 결과 (pgvector cosine) [출처: analytics.embedding_documents]"]
    for h in hits:
        lines.append(f"  - [{h['doc_type']} ref={h['ref_id']} score={h['score']:.3f}] {h['content']}")
    return hits, "\n".join(lines)


# --------------------------------------------------------------------------- #
# Stage 3 — Gemini generation
# --------------------------------------------------------------------------- #
def build_prompt(question: str, sql_context: str, vector_context: str) -> str:
    return (
        f"{SYSTEM_GUIDANCE}\n\n"
        f"=== SQL 실측 데이터 ===\n{sql_context}\n\n"
        f"=== 검색된 유사 사례 ===\n{vector_context}\n\n"
        f"=== 질문 ===\n{question}\n"
    )


_TRANSIENT = ("503", "unavailable", "429", "resource_exhausted", "overloaded", "high demand")


def generate(prompt: str, model: str = GEMINI_MODEL, max_retries: int = 4) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Get a free key at aistudio.google.com and add it to .env."
        )
    import time

    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            return resp.text or ""
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if not any(t in msg for t in _TRANSIENT):
                raise
            last_exc = exc
            delay = 2 ** attempt
            print(f"      [retry {attempt + 1}/{max_retries}] Gemini 일시 오류, {delay}s 후 재시도 ...")
            time.sleep(delay)
    raise RuntimeError(f"Gemini unavailable after {max_retries} retries: {last_exc}")
