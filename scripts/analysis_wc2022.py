"""WC2022 exploratory analysis queries — validation + story data."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import bootstrap

bootstrap()

from football.config import COMPETITION_ID, KOREA_TEAM_ID, SEASON_ID
from football.db.connection import get_connection


def json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(type(obj))


def run(cur, title: str, sql: str, params=None):
    cur.execute(sql, params or ())
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    print(f"\n=== {title} ===")
    for row in rows[:15]:
        print(row)
    if len(rows) > 15:
        print(f"... ({len(rows)} rows total)")
    return rows


def main() -> None:
    conn = get_connection()
    cur = conn.cursor()
    results: dict[str, list] = {}

    # Validation baseline
    results["validation"] = run(
        cur,
        "Validation counts",
        """
        SELECT 'matches' AS item, COUNT(*)::int AS n
        FROM staging.matches WHERE competition_id=%s AND season_id=%s
        UNION ALL
        SELECT 'events', COUNT(*)::int FROM staging.events
        UNION ALL
        SELECT 'fact', COUNT(*)::int FROM analytics.fact_player_match_stats
        UNION ALL
        SELECT 'formation', COUNT(*)::int FROM analytics.team_match_formation
        """,
        (COMPETITION_ID, SEASON_ID),
    )

    # 1. Goals by stage
    results["goals_by_stage"] = run(
        cur,
        "Q1 Goals by tournament stage",
        """
        WITH stage_order AS (
            SELECT * FROM (VALUES
                ('Group Stage', 1),
                ('Round of 16', 2),
                ('Quarter-finals', 3),
                ('Semi-finals', 4),
                ('3rd Place Final', 5),
                ('Final', 6)
            ) AS t(competition_stage, stage_rank)
        )
        SELECT
            m.competition_stage,
            COUNT(*)::int AS matches,
            ROUND(AVG(m.home_score + m.away_score)::numeric, 2) AS avg_total_goals,
            SUM(m.home_score + m.away_score)::int AS total_goals
        FROM staging.matches m
        JOIN stage_order so ON so.competition_stage = m.competition_stage
        WHERE m.competition_id = %s AND m.season_id = %s
        GROUP BY m.competition_stage, so.stage_rank
        ORDER BY so.stage_rank
        """,
        (COMPETITION_ID, SEASON_ID),
    )

    # 2. Best chance creators (xG)
    results["top_xg"] = run(
        cur,
        "Q2 Top chance creators (total xG)",
        """
        SELECT
            p.player_name,
            t.team_name,
            SUM(f.xg)::numeric(8,3) AS total_xg,
            SUM(f.shots)::int AS shots,
            SUM(f.goals)::int AS goals,
            ROUND(SUM(f.minutes_played)::numeric / NULLIF(COUNT(DISTINCT f.match_id), 0), 1) AS avg_mins_per_match
        FROM analytics.fact_player_match_stats f
        JOIN staging.players p ON p.player_id = f.player_id
        JOIN staging.teams t ON t.team_id = f.team_id
        JOIN staging.matches m ON m.match_id = f.match_id
        WHERE m.competition_id = %s AND m.season_id = %s
        GROUP BY p.player_id, p.player_name, t.team_name
        HAVING SUM(f.xg) > 0
        ORDER BY total_xg DESC
        LIMIT 10
        """,
        (COMPETITION_ID, SEASON_ID),
    )

    # 3. Pass accuracy vs winning
    results["pass_accuracy_vs_result"] = run(
        cur,
        "Q3 Team pass accuracy vs match result",
        """
        WITH team_match_passes AS (
            SELECT
                m.match_id,
                tm.team_id,
                tm.team_name,
                CASE
                    WHEN m.home_team_id = tm.team_id AND m.home_score > m.away_score THEN 'win'
                    WHEN m.away_team_id = tm.team_id AND m.away_score > m.home_score THEN 'win'
                    WHEN m.home_score = m.away_score THEN 'draw'
                    ELSE 'loss'
                END AS result,
                SUM(f.passes_attempted)::int AS passes_attempted,
                SUM(f.passes_completed)::int AS passes_completed
            FROM staging.matches m
            CROSS JOIN LATERAL (VALUES
                (m.home_team_id), (m.away_team_id)
            ) AS sides(team_id)
            JOIN staging.teams tm ON tm.team_id = sides.team_id
            JOIN analytics.fact_player_match_stats f
                ON f.match_id = m.match_id AND f.team_id = sides.team_id
            WHERE m.competition_id = %s AND m.season_id = %s
            GROUP BY m.match_id, tm.team_id, tm.team_name, result
        )
        SELECT
            result,
            COUNT(*)::int AS team_matches,
            ROUND(AVG(
                passes_completed::numeric / NULLIF(passes_attempted, 0)
            ), 4) AS avg_pass_completion_rate,
            ROUND(AVG(passes_attempted)::numeric, 1) AS avg_passes_attempted
        FROM team_match_passes
        WHERE passes_attempted > 0
        GROUP BY result
        ORDER BY CASE result WHEN 'win' THEN 1 WHEN 'draw' THEN 2 ELSE 3 END
        """,
        (COMPETITION_ID, SEASON_ID),
    )

    # 4. Pass accuracy under pressure
    results["pass_under_pressure"] = run(
        cur,
        "Q4 Pass completion under pressure",
        """
        SELECT
            CASE WHEN under_pressure IS TRUE THEN 'under_pressure'
                 ELSE 'no_pressure' END AS pressure_state,
            COUNT(*)::int AS pass_attempts,
            COUNT(*) FILTER (WHERE outcome IS NULL)::int AS passes_completed,
            ROUND(
                COUNT(*) FILTER (WHERE outcome IS NULL)::numeric
                / NULLIF(COUNT(*), 0),
                4
            ) AS completion_rate
        FROM staging.events
        WHERE type = 'Pass'
        GROUP BY 1
        ORDER BY 1
        """,
    )

    results["pass_pressure_drop"] = run(
        cur,
        "Q4b Pressure pass drop (percentage points)",
        """
        WITH rates AS (
            SELECT
                CASE WHEN under_pressure IS TRUE THEN 'under_pressure'
                     ELSE 'no_pressure' END AS pressure_state,
                COUNT(*) FILTER (WHERE outcome IS NULL)::numeric
                / NULLIF(COUNT(*), 0) AS rate
            FROM staging.events
            WHERE type = 'Pass'
            GROUP BY 1
        )
        SELECT
            ROUND(MAX(rate) FILTER (WHERE pressure_state = 'no_pressure'), 4) AS rate_no_pressure,
            ROUND(MAX(rate) FILTER (WHERE pressure_state = 'under_pressure'), 4) AS rate_under_pressure,
            ROUND((
                MAX(rate) FILTER (WHERE pressure_state = 'no_pressure')
                - MAX(rate) FILTER (WHERE pressure_state = 'under_pressure')
            ) * 100, 2) AS drop_pp
        FROM rates
        """,
    )

    # 5. Korea opponents defensive contribution
    results["korea_opponent_defense"] = run(
        cur,
        "Q5 Korea matches — opponent defensive actions",
        """
        WITH korea_matches AS (
            SELECT
                m.match_id,
                m.competition_stage,
                m.match_date,
                CASE WHEN m.home_team_id = %s THEN m.away_team_id ELSE m.home_team_id END AS opponent_id,
                ot.team_name AS opponent_name,
                m.home_score,
                m.away_score,
                CASE WHEN m.home_team_id = %s THEN 'home' ELSE 'away' END AS korea_side
            FROM staging.matches m
            JOIN staging.teams ot ON ot.team_id = CASE
                WHEN m.home_team_id = %s THEN m.away_team_id ELSE m.home_team_id
            END
            WHERE m.competition_id = %s AND m.season_id = %s
              AND (m.home_team_id = %s OR m.away_team_id = %s)
        )
        SELECT
            km.match_date,
            km.competition_stage,
            km.opponent_name,
            km.home_score || '-' || km.away_score AS score,
            km.korea_side,
            SUM(f.tackles)::int AS opp_tackles,
            SUM(f.interceptions)::int AS opp_interceptions,
            SUM(f.pressures)::int AS opp_pressures,
            SUM(f.blocks)::int AS opp_blocks,
            SUM(f.tackles + f.interceptions + f.pressures + f.blocks)::int AS opp_def_actions
        FROM korea_matches km
        JOIN analytics.fact_player_match_stats f
            ON f.match_id = km.match_id AND f.team_id = km.opponent_id
        GROUP BY km.match_id, km.match_date, km.competition_stage,
                 km.opponent_name, km.home_score, km.away_score, km.korea_side
        ORDER BY km.match_date
        """,
        (KOREA_TEAM_ID, KOREA_TEAM_ID, KOREA_TEAM_ID, COMPETITION_ID, SEASON_ID, KOREA_TEAM_ID, KOREA_TEAM_ID),
    )

    # Extra 1: xG over/underperformance (finishing)
    results["xg_overperformance"] = run(
        cur,
        "E1 Finishing efficiency (goals - xG, min 3 shots)",
        """
        SELECT
            p.player_name,
            t.team_name,
            SUM(f.goals)::int AS goals,
            ROUND(SUM(f.xg)::numeric, 3) AS total_xg,
            ROUND((SUM(f.goals) - SUM(f.xg))::numeric, 3) AS goals_minus_xg,
            SUM(f.shots)::int AS shots
        FROM analytics.fact_player_match_stats f
        JOIN staging.players p ON p.player_id = f.player_id
        JOIN staging.teams t ON t.team_id = f.team_id
        JOIN staging.matches m ON m.match_id = f.match_id
        WHERE m.competition_id = %s AND m.season_id = %s
        GROUP BY p.player_id, p.player_name, t.team_name
        HAVING SUM(f.shots) >= 3
        ORDER BY goals_minus_xg DESC
        LIMIT 8
        """,
        (COMPETITION_ID, SEASON_ID),
    )

    # Extra 2: Knockout defensive intensity (def actions per match by stage)
    results["def_intensity_by_stage"] = run(
        cur,
        "E2 Defensive actions per match by stage",
        """
        WITH stage_order AS (
            SELECT * FROM (VALUES
                ('Group Stage', 1), ('Round of 16', 2), ('Quarter-finals', 3),
                ('Semi-finals', 4), ('3rd Place Final', 5), ('Final', 6)
            ) AS t(competition_stage, stage_rank)
        ),
        match_def AS (
            SELECT
                m.match_id,
                m.competition_stage,
                SUM(f.tackles + f.interceptions + f.pressures + f.blocks) AS def_actions
            FROM staging.matches m
            JOIN analytics.fact_player_match_stats f ON f.match_id = m.match_id
            WHERE m.competition_id = %s AND m.season_id = %s
            GROUP BY m.match_id, m.competition_stage
        )
        SELECT
            md.competition_stage,
            COUNT(*)::int AS matches,
            ROUND(AVG(md.def_actions)::numeric, 0) AS avg_def_actions_per_match
        FROM match_def md
        JOIN stage_order so ON so.competition_stage = md.competition_stage
        GROUP BY md.competition_stage, so.stage_rank
        ORDER BY so.stage_rank
        """,
        (COMPETITION_ID, SEASON_ID),
    )

    # Extra 3: Korea xG for/against in their campaign
    results["korea_xg_balance"] = run(
        cur,
        "E3 Korea xG balance by match",
        """
        WITH korea_matches AS (
            SELECT m.match_id, m.match_date, m.competition_stage,
                ot.team_name AS opponent,
                m.home_score, m.away_score
            FROM staging.matches m
            JOIN staging.teams ot ON ot.team_id = CASE
                WHEN m.home_team_id = %s THEN m.away_team_id ELSE m.home_team_id
            END
            WHERE m.competition_id = %s AND m.season_id = %s
              AND (m.home_team_id = %s OR m.away_team_id = %s)
        )
        SELECT
            km.match_date,
            km.competition_stage,
            km.opponent,
            km.home_score || '-' || km.away_score AS score,
            ROUND(SUM(f.xg) FILTER (WHERE f.team_id = %s)::numeric, 2) AS korea_xg,
            ROUND(SUM(f.xg) FILTER (WHERE f.team_id <> %s)::numeric, 2) AS opp_xg,
            ROUND((
                SUM(f.xg) FILTER (WHERE f.team_id = %s)
                - SUM(f.xg) FILTER (WHERE f.team_id <> %s)
            )::numeric, 2) AS xg_diff
        FROM korea_matches km
        JOIN analytics.fact_player_match_stats f ON f.match_id = km.match_id
        GROUP BY km.match_id, km.match_date, km.competition_stage, km.opponent,
                 km.home_score, km.away_score
        ORDER BY km.match_date
        """,
        (KOREA_TEAM_ID, COMPETITION_ID, SEASON_ID, KOREA_TEAM_ID, KOREA_TEAM_ID,
         KOREA_TEAM_ID, KOREA_TEAM_ID, KOREA_TEAM_ID, KOREA_TEAM_ID),
    )

    out = Path(__file__).resolve().parents[1] / "explore" / "analysis_wc2022_results.json"
    out.write_text(json.dumps(results, indent=2, default=json_default), encoding="utf-8")
    print(f"\n[saved] {out}")

    conn.close()


if __name__ == "__main__":
    main()
