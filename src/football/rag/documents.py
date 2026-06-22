"""Build natural-language RAG documents from WC2022 analytics SQL.

Three doc_types, all Korea-centric (Day 5 demo = Korea vs Brazil):
  - match_report     (ref_id=match_id)  : Korea's matches — score, xG balance, defensive output
  - tactical_pattern (ref_id=team_id)   : Korea + opponents — formations + defensive/attacking profile
  - player_profile   (ref_id=player_id) : Korea + Brazil players — aggregated WC2022 stats

Documents are deterministic templates (no LLM) and stored in analytics.embedding_documents
with embedding left NULL — football.rag.embedder fills it. Rebuild is idempotent
(DELETE by doc_type, then INSERT).
"""
from __future__ import annotations

from psycopg2.extensions import connection as PGConnection
from psycopg2.extras import Json

from football.config import BRAZIL_TEAM_ID, COMPETITION_ID, KOREA_TEAM_ID, SEASON_ID

DOC_TYPES = ("match_report", "tactical_pattern", "player_profile")


def _rows(cur, sql: str, params) -> list[dict]:
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# --------------------------------------------------------------------------- #
# Source queries
# --------------------------------------------------------------------------- #
def korea_matches(cur, competition_id: int, season_id: int) -> list[dict]:
    """Korea's matches with opponent, score, xG balance (E3 logic) and defensive output (Q5 logic)."""
    sql = """
        WITH km AS (
            SELECT m.match_id, m.match_date, m.competition_stage,
                CASE WHEN m.home_team_id = %(k)s THEN m.away_team_id ELSE m.home_team_id END AS opponent_id,
                CASE WHEN m.home_team_id = %(k)s THEN m.home_score ELSE m.away_score END AS korea_score,
                CASE WHEN m.home_team_id = %(k)s THEN m.away_score ELSE m.home_score END AS opp_score
            FROM staging.matches m
            WHERE m.competition_id = %(c)s AND m.season_id = %(s)s
              AND (m.home_team_id = %(k)s OR m.away_team_id = %(k)s)
        )
        SELECT km.match_id, km.match_date, km.competition_stage,
            km.opponent_id, ot.team_name AS opponent_name,
            km.korea_score, km.opp_score,
            ROUND(SUM(f.xg) FILTER (WHERE f.team_id = %(k)s)::numeric, 2) AS korea_xg,
            ROUND(SUM(f.xg) FILTER (WHERE f.team_id <> %(k)s)::numeric, 2) AS opp_xg,
            SUM(f.tackles + f.interceptions + f.pressures + f.blocks)
                FILTER (WHERE f.team_id = %(k)s)::int AS korea_def_actions,
            SUM(f.tackles + f.interceptions + f.pressures + f.blocks)
                FILTER (WHERE f.team_id <> %(k)s)::int AS opp_def_actions
        FROM km
        JOIN staging.teams ot ON ot.team_id = km.opponent_id
        JOIN analytics.fact_player_match_stats f ON f.match_id = km.match_id
        GROUP BY km.match_id, km.match_date, km.competition_stage,
                 km.opponent_id, ot.team_name, km.korea_score, km.opp_score
        ORDER BY km.match_date
    """
    return _rows(cur, sql, {"k": KOREA_TEAM_ID, "c": competition_id, "s": season_id})


def team_aggregates(cur, competition_id: int, season_id: int, team_ids: list[int]) -> list[dict]:
    sql = """
        SELECT f.team_id, t.team_name,
            COUNT(DISTINCT f.match_id)::int AS matches,
            SUM(f.goals)::int AS goals,
            ROUND(SUM(f.xg)::numeric, 2) AS xg,
            SUM(f.passes_attempted)::int AS passes_attempted,
            SUM(f.passes_completed)::int AS passes_completed,
            SUM(f.tackles)::int AS tackles,
            SUM(f.interceptions)::int AS interceptions,
            SUM(f.pressures)::int AS pressures,
            SUM(f.blocks)::int AS blocks
        FROM analytics.fact_player_match_stats f
        JOIN staging.teams t ON t.team_id = f.team_id
        JOIN staging.matches m ON m.match_id = f.match_id
        WHERE m.competition_id = %(c)s AND m.season_id = %(s)s AND f.team_id = ANY(%(ids)s)
        GROUP BY f.team_id, t.team_name
        ORDER BY f.team_id
    """
    return _rows(cur, sql, {"c": competition_id, "s": season_id, "ids": team_ids})


def team_formations(cur, competition_id: int, season_id: int, team_ids: list[int]) -> dict[int, list[str]]:
    """team_id -> ordered, de-duplicated list of formation codes used across their matches."""
    sql = """
        SELECT tmf.team_id, tmf.formation_code
        FROM analytics.team_match_formation tmf
        JOIN staging.matches m ON m.match_id = tmf.match_id
        WHERE m.competition_id = %(c)s AND m.season_id = %(s)s AND tmf.team_id = ANY(%(ids)s)
        ORDER BY tmf.team_id, tmf.match_id, tmf.from_minute
    """
    out: dict[int, list[str]] = {}
    for r in _rows(cur, sql, {"c": competition_id, "s": season_id, "ids": team_ids}):
        seq = out.setdefault(r["team_id"], [])
        if not seq or seq[-1] != r["formation_code"]:
            seq.append(r["formation_code"])
    # collapse to distinct preserving first-seen order
    for tid, seq in out.items():
        seen: list[str] = []
        for f in seq:
            if f not in seen:
                seen.append(f)
        out[tid] = seen
    return out


def player_profiles(cur, competition_id: int, season_id: int, team_ids: list[int]) -> list[dict]:
    sql = """
        SELECT p.player_id, p.player_name, f.team_id, t.team_name,
            COUNT(DISTINCT f.match_id)::int AS matches,
            ROUND(SUM(f.minutes_played)::numeric, 0) AS minutes,
            (SELECT f2.position_played
               FROM analytics.fact_player_match_stats f2
               WHERE f2.player_id = p.player_id AND f2.position_played IS NOT NULL
               GROUP BY f2.position_played
               ORDER BY SUM(f2.minutes_played) DESC NULLS LAST
               LIMIT 1) AS position,
            SUM(f.passes_attempted)::int AS passes_attempted,
            SUM(f.passes_completed)::int AS passes_completed,
            SUM(f.goals)::int AS goals,
            SUM(f.assists)::int AS assists,
            SUM(f.shots)::int AS shots,
            ROUND(SUM(f.xg)::numeric, 2) AS xg,
            SUM(f.tackles)::int AS tackles,
            SUM(f.interceptions)::int AS interceptions,
            SUM(f.pressures)::int AS pressures,
            SUM(f.blocks)::int AS blocks
        FROM analytics.fact_player_match_stats f
        JOIN staging.players p ON p.player_id = f.player_id
        JOIN staging.teams t ON t.team_id = f.team_id
        JOIN staging.matches m ON m.match_id = f.match_id
        WHERE m.competition_id = %(c)s AND m.season_id = %(s)s AND f.team_id = ANY(%(ids)s)
        GROUP BY p.player_id, p.player_name, f.team_id, t.team_name
        HAVING SUM(f.minutes_played) > 0
        ORDER BY f.team_id, minutes DESC
    """
    return _rows(cur, sql, {"c": competition_id, "s": season_id, "ids": team_ids})


# --------------------------------------------------------------------------- #
# Templates  ->  (doc_type, ref_id, content, metadata)
# --------------------------------------------------------------------------- #
def _pct(completed: int, attempted: int) -> str:
    return f"{(completed / attempted * 100):.1f}%" if attempted else "n/a"


def build_match_reports(matches: list[dict]) -> list[tuple]:
    docs = []
    for m in matches:
        result = ("win" if m["korea_score"] > m["opp_score"]
                  else "loss" if m["korea_score"] < m["opp_score"] else "draw")
        content = (
            f"World Cup 2022 match report — South Korea {m['korea_score']}-{m['opp_score']} "
            f"{m['opponent_name']} ({m['competition_stage']}, {m['match_date']}). "
            f"Result: Korea {result}. "
            f"Expected goals: Korea {m['korea_xg']} xG vs {m['opponent_name']} {m['opp_xg']} xG. "
            f"Defensive actions (tackles+interceptions+pressures+blocks): "
            f"Korea {m['korea_def_actions']}, {m['opponent_name']} {m['opp_def_actions']}. "
            f"{m['opponent_name']} applied {m['opp_def_actions']} defensive actions against Korea, "
            f"indicating {'a high-intensity pressing approach' if m['opp_def_actions'] >= 160 else 'a measured defensive approach'}."
        )
        docs.append((
            "match_report", int(m["match_id"]), content,
            {
                "match_id": int(m["match_id"]),
                "opponent_id": int(m["opponent_id"]),
                "opponent_name": m["opponent_name"],
                "stage": m["competition_stage"],
                "korea_score": int(m["korea_score"]),
                "opp_score": int(m["opp_score"]),
                "korea_xg": float(m["korea_xg"] or 0),
                "opp_xg": float(m["opp_xg"] or 0),
                "opp_def_actions": int(m["opp_def_actions"] or 0),
            },
        ))
    return docs


def build_tactical_patterns(aggs: list[dict], formations: dict[int, list[str]]) -> list[tuple]:
    docs = []
    for a in aggs:
        tid = a["team_id"]
        forms = formations.get(tid, [])
        forms_txt = ", ".join(forms) if forms else "n/a"
        content = (
            f"Tactical pattern — {a['team_name']} at World Cup 2022 ({a['matches']} matches). "
            f"Formations used: {forms_txt}. "
            f"Defensive profile: {a['tackles']} tackles, {a['interceptions']} interceptions, "
            f"{a['pressures']} pressures, {a['blocks']} blocks. "
            f"Attacking output: {a['goals']} goals, {a['xg']} xG, "
            f"pass completion {_pct(a['passes_completed'], a['passes_attempted'])} "
            f"({a['passes_completed']}/{a['passes_attempted']})."
        )
        docs.append((
            "tactical_pattern", int(tid), content,
            {
                "team_id": int(tid),
                "team_name": a["team_name"],
                "formations": forms,
                "matches": int(a["matches"]),
                "tackles": int(a["tackles"]),
                "interceptions": int(a["interceptions"]),
                "pressures": int(a["pressures"]),
                "blocks": int(a["blocks"]),
                "goals": int(a["goals"]),
                "xg": float(a["xg"] or 0),
            },
        ))
    return docs


def build_player_profiles(players: list[dict]) -> list[tuple]:
    docs = []
    for p in players:
        content = (
            f"Player profile — {p['player_name']} ({p['team_name']}, {p['position'] or 'unknown position'}) "
            f"at World Cup 2022: {p['matches']} matches, {p['minutes']} minutes. "
            f"Attacking: {p['goals']} goals, {p['assists']} assists, {p['shots']} shots, {p['xg']} xG. "
            f"Passing: {p['passes_completed']}/{p['passes_attempted']} "
            f"({_pct(p['passes_completed'], p['passes_attempted'])}). "
            f"Defending: {p['tackles']} tackles, {p['interceptions']} interceptions, "
            f"{p['pressures']} pressures, {p['blocks']} blocks."
        )
        docs.append((
            "player_profile", int(p["player_id"]), content,
            {
                "player_id": int(p["player_id"]),
                "player_name": p["player_name"],
                "team_id": int(p["team_id"]),
                "team_name": p["team_name"],
                "position": p["position"],
                "minutes": float(p["minutes"] or 0),
                "goals": int(p["goals"]),
                "assists": int(p["assists"]),
                "xg": float(p["xg"] or 0),
            },
        ))
    return docs


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def generate_documents(
    conn: PGConnection,
    competition_id: int = COMPETITION_ID,
    season_id: int = SEASON_ID,
    doc_types: tuple[str, ...] = DOC_TYPES,
) -> dict[str, int]:
    """Rebuild the requested doc_types in analytics.embedding_documents (idempotent).

    Returns a {doc_type: row_count} summary. Embeddings are left NULL.
    """
    with conn.cursor() as cur:
        matches = korea_matches(cur, competition_id, season_id)
        opponent_ids = sorted({m["opponent_id"] for m in matches})
        tactical_team_ids = sorted({KOREA_TEAM_ID, *opponent_ids})
        player_team_ids = sorted({KOREA_TEAM_ID, BRAZIL_TEAM_ID})

        all_docs: list[tuple] = []
        if "match_report" in doc_types:
            all_docs += build_match_reports(matches)
        if "tactical_pattern" in doc_types:
            aggs = team_aggregates(cur, competition_id, season_id, tactical_team_ids)
            forms = team_formations(cur, competition_id, season_id, tactical_team_ids)
            all_docs += build_tactical_patterns(aggs, forms)
        if "player_profile" in doc_types:
            players = player_profiles(cur, competition_id, season_id, player_team_ids)
            all_docs += build_player_profiles(players)

        # idempotent rebuild of just the requested types
        cur.execute(
            "DELETE FROM analytics.embedding_documents WHERE doc_type = ANY(%s)",
            (list(doc_types),),
        )
        summary: dict[str, int] = {dt: 0 for dt in doc_types}
        for doc_type, ref_id, content, metadata in all_docs:
            cur.execute(
                """
                INSERT INTO analytics.embedding_documents
                    (doc_type, ref_id, content, metadata, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (doc_type, ref_id, content, Json(metadata)),
            )
            summary[doc_type] = summary.get(doc_type, 0) + 1
    conn.commit()
    return summary
