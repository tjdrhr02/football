WITH scoped_matches AS (
    SELECT unnest(%(match_ids)s::int[]) AS match_id
),
event_stats AS (
    SELECT
        e.match_id,
        e.player_id,
        MAX(e.team_id) AS team_id,
        COUNT(*) FILTER (WHERE e.type = 'Pass') AS passes_attempted,
        COUNT(*) FILTER (WHERE e.type = 'Pass' AND e.outcome IS NULL) AS passes_completed,
        COUNT(*) FILTER (WHERE e.type = 'Shot') AS shots,
        COUNT(*) FILTER (
            WHERE e.type = 'Shot' AND e.outcome IN ('Saved', 'Goal')
        ) AS shots_on_target,
        COUNT(*) FILTER (WHERE e.type = 'Shot' AND e.outcome = 'Goal') AS goals,
        COUNT(*) FILTER (
            WHERE e.type = 'Pass' AND e.payload->>'pass_goal_assist' IS NOT NULL
        ) AS assists,
        COALESCE(SUM(e.shot_statsbomb_xg) FILTER (WHERE e.type = 'Shot'), 0) AS xg,
        COUNT(*) FILTER (WHERE e.type = 'Pressure') AS pressures,
        COUNT(*) FILTER (
            WHERE e.type = 'Duel' AND e.payload->>'duel_type' = 'Tackle'
        ) AS tackles,
        COUNT(*) FILTER (WHERE e.type = 'Interception') AS interceptions,
        COUNT(*) FILTER (WHERE e.type = 'Block') AS blocks,
        COUNT(*) FILTER (WHERE e.type = 'Dribble') AS dribbles_attempted,
        COUNT(*) FILTER (WHERE e.type = 'Dribble' AND e.outcome IS NULL) AS dribbles_completed,
        COUNT(*) FILTER (WHERE e.type = 'Carry') AS carries,
        COUNT(*) FILTER (
            WHERE e.type = 'Foul Committed'
              AND e.payload->>'foul_committed_card' = 'Yellow Card'
        ) + COUNT(*) FILTER (
            WHERE e.type = 'Bad Behaviour'
              AND e.payload->>'bad_behaviour_card' = 'Yellow Card'
        ) AS yellow_cards,
        COUNT(*) FILTER (
            WHERE e.type = 'Foul Committed'
              AND e.payload->>'foul_committed_card' IN ('Red Card', 'Second Yellow')
        ) + COUNT(*) FILTER (
            WHERE e.type = 'Bad Behaviour'
              AND e.payload->>'bad_behaviour_card' IN ('Red Card', 'Second Yellow')
        ) AS red_cards
    FROM staging.events e
    INNER JOIN scoped_matches sm ON sm.match_id = e.match_id
    WHERE e.player_id IS NOT NULL
    GROUP BY e.match_id, e.player_id
),
match_max_minute AS (
    SELECT e.match_id, MAX(e.minute)::smallint AS max_minute
    FROM staging.events e
    INNER JOIN scoped_matches sm ON sm.match_id = e.match_id
    WHERE e.minute IS NOT NULL
    GROUP BY e.match_id
),
minutes AS (
    SELECT
        ml.match_id,
        ml.player_id,
        SUM(
            CASE
                WHEN mlp.from_minute IS NULL THEN 0
                WHEN mlp.to_minute IS NOT NULL THEN GREATEST(mlp.to_minute - mlp.from_minute, 0)
                ELSE GREATEST(mm.max_minute - mlp.from_minute, 0)
            END
        )::decimal(6, 2) AS minutes_played
    FROM staging.match_lineups ml
    INNER JOIN staging.match_lineup_positions mlp ON mlp.lineup_id = ml.lineup_id
    INNER JOIN scoped_matches sm ON sm.match_id = ml.match_id
    INNER JOIN match_max_minute mm ON mm.match_id = ml.match_id
    GROUP BY ml.match_id, ml.player_id
),
primary_position AS (
    SELECT DISTINCT ON (ml.match_id, ml.player_id)
        ml.match_id,
        ml.player_id,
        mlp.position_name AS position_played
    FROM staging.match_lineups ml
    INNER JOIN staging.match_lineup_positions mlp ON mlp.lineup_id = ml.lineup_id
    INNER JOIN scoped_matches sm ON sm.match_id = ml.match_id
    INNER JOIN match_max_minute mm ON mm.match_id = ml.match_id
    ORDER BY
        ml.match_id,
        ml.player_id,
        (
            CASE
                WHEN mlp.from_minute IS NULL THEN 0
                WHEN mlp.to_minute IS NOT NULL THEN GREATEST(mlp.to_minute - mlp.from_minute, 0)
                ELSE GREATEST(mm.max_minute - mlp.from_minute, 0)
            END
        ) DESC,
        mlp.from_period,
        mlp.from_minute
),
lineup_info AS (
    SELECT
        ml.match_id,
        ml.player_id,
        ml.team_id,
        ml.is_starter
    FROM staging.match_lineups ml
    INNER JOIN scoped_matches sm ON sm.match_id = ml.match_id
)
INSERT INTO analytics.fact_player_match_stats (
    match_id,
    player_id,
    team_id,
    minutes_played,
    is_starter,
    position_played,
    passes_attempted,
    passes_completed,
    pass_completion_rate,
    progressive_passes,
    shots,
    shots_on_target,
    goals,
    assists,
    xg,
    xa,
    tackles,
    interceptions,
    pressures,
    blocks,
    dribbles_attempted,
    dribbles_completed,
    carries,
    yellow_cards,
    red_cards,
    aggregated_at
)
SELECT
    es.match_id,
    es.player_id,
    COALESCE(li.team_id, es.team_id) AS team_id,
    COALESCE(m.minutes_played, 0) AS minutes_played,
    COALESCE(li.is_starter, FALSE) AS is_starter,
    pp.position_played,
    es.passes_attempted,
    es.passes_completed,
    CASE
        WHEN es.passes_attempted > 0
        THEN ROUND(es.passes_completed::numeric / es.passes_attempted, 4)
    END AS pass_completion_rate,
    NULL::integer AS progressive_passes,
    es.shots,
    es.shots_on_target,
    es.goals,
    es.assists,
    es.xg,
    0::decimal(6, 4) AS xa,
    es.tackles,
    es.interceptions,
    es.pressures,
    es.blocks,
    es.dribbles_attempted,
    es.dribbles_completed,
    es.carries,
    es.yellow_cards::smallint,
    es.red_cards::smallint,
    now() AS aggregated_at
FROM event_stats es
LEFT JOIN minutes m
    ON m.match_id = es.match_id AND m.player_id = es.player_id
LEFT JOIN lineup_info li
    ON li.match_id = es.match_id AND li.player_id = es.player_id
LEFT JOIN primary_position pp
    ON pp.match_id = es.match_id AND pp.player_id = es.player_id
WHERE COALESCE(li.team_id, es.team_id) IS NOT NULL
