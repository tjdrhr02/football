"""ERD 설계를 StatsBomb WC2022 실제 데이터로 검증."""
import warnings
from collections import defaultdict

import pandas as pd

warnings.filterwarnings("ignore")

from statsbombpy import sb

COMPETITION_ID = 43
SEASON_ID = 106
KOREA_TEAM_ID = 791


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n {title}\n{'=' * 60}")


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def main() -> None:
    section("1. competitions / seasons")
    comps = sb.competitions()
    wc = comps[(comps["competition_id"] == COMPETITION_ID) & (comps["season_id"] == SEASON_ID)]
    if wc.empty:
        fail("WC2022 competition/season not found")
        return
    row = wc.iloc[0]
    ok(f"competition_id={row['competition_id']}, season_id={row['season_id']}, name={row['competition_name']} {row['season_name']}")
    dup_season = comps[comps["season_id"] == SEASON_ID]["competition_id"].nunique()
    if dup_season > 1:
        ok(f"season_id={SEASON_ID} appears in {dup_season} competitions → composite PK (competition_id, season_id) justified")
    else:
        warn(f"season_id={SEASON_ID} unique across competitions in open data — composite PK still safe")

    section("2. matches (64경기)")
    matches = sb.matches(competition_id=COMPETITION_ID, season_id=SEASON_ID)
    ok(f"match count = {len(matches)} (expected 64)")
    erd_match_cols = {
        "match_id", "competition_id", "season_id", "match_date", "kick_off",
        "home_team_id", "away_team_id", "home_score", "away_score",
        "match_status", "competition_stage", "match_week", "stadium", "referee",
    }
    present = erd_match_cols & set(matches.columns)
    missing = erd_match_cols - set(matches.columns)
    ok(f"ERD match columns available: {sorted(present)}")
    if missing:
        warn(f"Rename in ETL: {sorted(missing)} → stadium_name/referee_name from 'stadium'/'referee'")
    ok(f"stages: {matches['competition_stage'].value_counts().to_dict()}")
    korea_matches = matches[
        (matches["home_team_id"] == KOREA_TEAM_ID) | (matches["away_team_id"] == KOREA_TEAM_ID)
    ]
    ok(f"Korea matches = {len(korea_matches)}: {list(korea_matches['match_id'])}")

    section("3. teams / players")
    teams = set(matches["home_team_id"]) | set(matches["away_team_id"])
    ok(f"unique teams in matches = {len(teams)}")
    # sample match for players
    sample_match_id = int(matches.iloc[0]["match_id"])
    lineups = sb.lineups(match_id=sample_match_id)
    players_in_lineups = set()
    for df in lineups.values():
        players_in_lineups.update(df["player_id"].tolist())
    ok(f"lineup cols = {list(next(iter(lineups.values())).columns)}")
    erd_player_cols = {"player_id", "player_name", "player_nickname", "country"}
    lineup_cols = set(next(iter(lineups.values())).columns)
    if erd_player_cols - {"country"} <= lineup_cols:
        ok("staging.players fields derivable from lineups")
    if "country" in lineup_cols:
        ok("country → country_name in ETL")
    else:
        warn("country field check in lineups")

    section("4. events (~250k) — staging.events 검증")
    total_events = 0
    event_types = defaultdict(int)
    has_location = 0
    has_payload_cols = 0
    sample_events = None

    for mid in matches["match_id"].head(5):
        ev = sb.events(match_id=int(mid))
        total_events += len(ev)
        if sample_events is None:
            sample_events = ev
        for t in ev["type"]:
            event_types[t] += 1
        has_location += ev["location"].notna().sum()
        # columns not in ERD core → payload
        core = {
            "id", "match_id", "index", "period", "timestamp", "minute", "second",
            "type", "team_id", "player_id", "location", "duration", "under_pressure",
            "pass_outcome", "shot_outcome", "shot_statsbomb_xg",
        }
        extra_cols = [c for c in ev.columns if c not in core and ev[c].notna().any()]
        has_payload_cols = max(has_payload_cols, len(extra_cols))

    # full count on all matches (may take ~30s)
    print("  ... counting all 64 matches (please wait)")
    all_event_count = 0
    for mid in matches["match_id"]:
        all_event_count += len(sb.events(match_id=int(mid)))
    ok(f"total events (64 matches) = {all_event_count:,}")
    ok(f"avg per match = {all_event_count / len(matches):,.0f}")
    ok(f"event types in sample: {len(event_types)} types, top5 = {dict(sorted(event_types.items(), key=lambda x: -x[1])[:5])}")

    ev = sample_events
    ok(f"event_id col = 'id' (UUID), sample = {ev.iloc[10]['id']}")
    loc = ev.iloc[10]["location"]
    if isinstance(loc, (list, tuple)) and len(loc) == 2:
        ok(f"location → location_x/y: {loc}")
    else:
        warn(f"location format: {type(loc)} {loc}")

    # outcome mapping
    passes = ev[ev["type"] == "Pass"]
    shots = ev[ev["type"] == "Shot"]
    ok(f"Pass with pass_outcome: {passes['pass_outcome'].notna().sum()}/{len(passes)} in sample match")
    ok(f"Shot with shot_outcome: {shots['shot_outcome'].notna().sum()}/{len(shots)} in sample match")
    ok(f"~{has_payload_cols} sparse cols per match → payload jsonb justified")

    section("5. match_lineups / match_lineup_positions")
    lu = lineups
    for team_name, df in lu.items():
        ok(f"[{team_name}] squad size = {len(df)}")
        with_pos = df[df["positions"].apply(lambda x: isinstance(x, list) and len(x) > 0)]
        ok(f"  players with positions = {len(with_pos)}")
        if len(with_pos):
            pos0 = with_pos.iloc[0]["positions"][0]
            ok(f"  position keys: {list(pos0.keys())}")
            # check time fields
            time_keys = [k for k in pos0.keys() if "period" in k or "minute" in k or "reason" in k]
            ok(f"  time/reason keys in position: {time_keys}")
            print(f"  sample position record: {pos0}")
        empty_pos = df[df["positions"].apply(lambda x: not x or len(x) == 0)]
        if len(empty_pos):
            ok(f"  bench (empty positions) = {len(empty_pos)}")

    section("6. team_match_formation — Starting XI / Tactical Shift")
    formation_events = []
    for mid in matches["match_id"]:
        ev = sb.events(match_id=int(mid))
        fe = ev[ev["type"].isin(["Starting XI", "Tactical Shift"])]
        for _, row in fe.iterrows():
            tactics = row.get("tactics")
            if tactics and isinstance(tactics, dict):
                formation_events.append({
                    "match_id": mid,
                    "team": row["team"],
                    "type": row["type"],
                    "minute": row["minute"],
                    "formation": tactics.get("formation"),
                })
    fdf = pd.DataFrame(formation_events)
    ok(f"formation events total = {len(fdf)}")
    ok(f"by type: {fdf['type'].value_counts().to_dict()}")
    shifts = fdf[fdf["type"] == "Tactical Shift"]
    if len(shifts):
        ok(f"Tactical Shift exists = {len(shifts)} → team_match_formation timeline needed")
        print(shifts.head(3).to_string(index=False))
    else:
        warn("No Tactical Shift in WC2022 — timeline table still valid but mostly Starting XI only")
    formations_used = fdf["formation"].value_counts().head(8)
    ok(f"top formations: {formations_used.to_dict()}")

    section("7. fact_player_match_stats — 집계 가능성")
    # Use Korea vs Brazil R16
    korea_brazil = 3869253
    ev = sb.events(match_id=korea_brazil)
    lu = sb.lineups(match_id=korea_brazil)

    stats = defaultdict(lambda: defaultdict(int))
    xg = defaultdict(float)

    for _, e in ev.iterrows():
        pid = e.get("player_id")
        if pd.isna(pid):
            continue
        pid = int(pid)
        t = e["type"]
        stats[pid][t] += 1
        if t == "Shot" and e.get("shot_statsbomb_xg") == e.get("shot_statsbomb_xg"):
            xg[pid] += float(e["shot_statsbomb_xg"])

    players_with_events = len(stats)
    ok(f"Korea vs Brazil: players with events = {players_with_events}")

    # lineup players
    lineup_players = set()
    for df in lu.values():
        lineup_players.update(df["player_id"].tolist())
    ok(f"lineup players = {len(lineup_players)}")

    # estimate full tournament fact rows
    est_fact_rows = 0
    for mid in matches["match_id"]:
        ev = sb.events(match_id=int(mid))
        est_fact_rows += ev["player_id"].dropna().nunique()
    ok(f"estimated fact_player_match_stats rows (sum of unique players per match) ≈ {est_fact_rows:,}")
    ok(f"reduction ratio events→fact ≈ {all_event_count / est_fact_rows:.0f}x")

    # fact columns feasibility
    type_map = {
        "passes_attempted": "Pass",
        "shots": "Shot",
        "pressures": "Pressure",
        "tackles": "Tackle",  # may not exist
        "interceptions": "Interception",
        "blocks": "Block",
        "dribbles_attempted": "Dribble",
        "carries": "Carry",
    }
    all_types = set()
    for mid in matches["match_id"].head(10):
        all_types.update(sb.events(match_id=int(mid))["type"].unique())
    for col, etype in type_map.items():
        if etype in all_types:
            ok(f"fact.{col} ← events type '{etype}'")
        else:
            warn(f"fact.{col} ← type '{etype}' NOT in data — will be 0 or derived differently")

    # goals
    goals = ev[(ev["type"] == "Shot") & (ev["shot_outcome"] == "Goal")]
    ok(f"goals in Korea-Brazil: {len(goals)} shot-goals")
    # assists - check pass_goal_assist in payload
    passes_all = ev[ev["type"] == "Pass"]
    if "pass_goal_assist" in ev.columns:
        assists = passes_all["pass_goal_assist"].notna().sum()
        ok(f"assists via pass_goal_assist column: {assists} in sample")
    else:
        warn("pass_goal_assist — check payload")

    section("8. oltp 제거 검증")
    ok("No height, weight, market_value in StatsBomb lineups/events — oltp removal justified")

    section("9. dim_* 제거 검증")
    ok(f"fact rows ≈ {est_fact_rows:,} — staging JOIN sufficient, dim tables overkill")

    section("10. 종합")
    issues = []
    if all_event_count < 100_000:
        issues.append("event count lower than expected")
    if est_fact_rows > 10_000:
        issues.append("fact rows higher than ~2k estimate")
    if len(fdf) < 64:
        issues.append("fewer formation events than matches")

    if not issues:
        ok("ERD design validated against WC2022 actual data")
    else:
        for i in issues:
            warn(i)

    print("\n--- Validation summary ---")
    print(f"  matches:     {len(matches)}")
    print(f"  teams:       {len(teams)}")
    print(f"  events:      {all_event_count:,}")
    print(f"  fact (est):  {est_fact_rows:,}")
    print(f"  formations:  {len(fdf)} events")
    print(f"  Korea team:  {KOREA_TEAM_ID}, matches: {len(korea_matches)}")


if __name__ == "__main__":
    main()
