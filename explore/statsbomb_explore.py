"""StatsBomb Open Data exploration (no PostgreSQL required)."""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from statsbombpy import sb

from football.config import COMPETITION_ID, SEASON_ID


def section(title: str) -> None:
    width = 60
    print(f"\n{'=' * width}")
    print(f" {title}")
    print("=" * width)


def player_label(row) -> str:
    name = row.get("player_nickname") or row.get("player_name") or "?"
    jersey = row.get("jersey_number")
    return f"#{jersey} {name}" if jersey else name


def format_clock(minute, second) -> str:
    if minute is None:
        return "?"
    sec = int(second or 0)
    return f"{int(minute)}'{sec:02d}\""


def print_match_summary(match) -> None:
    home = match["home_team"]
    away = match["away_team"]
    score = f"{match['home_score']} - {match['away_score']}"
    date = match["match_date"]
    stadium = match.get("stadium") or "?"
    stage = match.get("competition_stage") or "?"
    comp = match.get("competition_name") or "?"
    season = match.get("season") or match.get("season_name") or "?"

    print(f"  {comp} {season} | {stage}")
    print(f"  {date}  |  {stadium}")
    print(f"  {home}  {score}  {away}")
    print(f"  match_id: {match['match_id']}")


def build_player_lookup(lineups: dict) -> dict:
    lookup = {}
    for df in lineups.values():
        for _, row in df.iterrows():
            lookup[row["player_id"]] = row
    return lookup


def print_lineups_from_events(events, lineups: dict) -> None:
    player_lookup = build_player_lookup(lineups)
    xi_events = events[events["type"] == "Starting XI"]

    for _, row in xi_events.iterrows():
        team = row["team"]
        tactics = row["tactics"] or {}
        formation = tactics.get("formation", "?")
        starter_ids = set()

        print(f"\n  [{team}] 포메이션 {formation}")
        for slot in tactics.get("lineup", []):
            player = slot.get("player", {})
            pid = player.get("id")
            starter_ids.add(pid)
            info = player_lookup.get(pid)
            if info is not None:
                label = player_label(info)
            else:
                jersey = player.get("jersey_number", "?")
                name = player.get("name", "?")
                label = f"#{jersey} {name}"
            pos = slot.get("position", {}).get("name", "?")
            print(f"    {label:<30} {pos}")

        bench = lineups[team]
        bench = bench[~bench["player_id"].isin(starter_ids)].sort_values("jersey_number")
        if len(bench):
            print(f"  벤치 {len(bench)}명")
            for _, p in bench.iterrows():
                print(f"    {player_label(p)}")


def build_short_names(lineups: dict) -> dict:
    names = {}
    for df in lineups.values():
        for _, row in df.iterrows():
            short = row.get("player_nickname") or row.get("player_name")
            names[row["player_id"]] = short
    return names


def print_goals(events, short_names: dict) -> None:
    goals = events[(events["type"] == "Shot") & (events["shot_outcome"] == "Goal")]
    if goals.empty:
        print("  (득점 이벤트 없음)")
        return

    regular = goals[goals["period"] <= 4]
    shootout = goals[goals["period"] == 5]

    def line(g):
        clock = format_clock(g["minute"], g["second"])
        pid = g.get("player_id")
        player = short_names.get(pid, g["player"])
        xg = g.get("shot_statsbomb_xg")
        xg_str = f" (xG {xg:.2f})" if xg == xg else ""
        shot_type = g.get("shot_type") or ""
        type_str = f" [{shot_type}]" if shot_type else ""
        return f"  {clock}  {g['team']:<12} {player}{type_str}{xg_str}"

    print("  정규 시간 + 연장")
    for _, g in regular.iterrows():
        print(line(g))

    if not shootout.empty:
        print("\n  승부차기")
        for _, g in shootout.iterrows():
            print(line(g))


def print_event_summary(events) -> None:
    counts = events["type"].value_counts()
    total = len(events)
    print(f"  총 이벤트: {total:,}개\n")
    print("  주요 이벤트 (상위 12개):")
    for event_type, count in counts.head(12).items():
        pct = count / total * 100
        bar = "#" * int(pct)
        print(f"    {event_type:<20} {count:>5}개  ({pct:4.1f}%)  {bar}")

    shots = events[events["type"] == "Shot"]
    if not shots.empty:
        print("\n  슛 / xG 요약:")
        for team, grp in shots.groupby("team"):
            goals = (grp["shot_outcome"] == "Goal").sum()
            print(
                f"    {team:<12} 슛 {len(grp):>2}개  "
                f"득점 {goals}  xG 합계 {grp['shot_statsbomb_xg'].sum():.2f}"
            )


def print_sample_events(events, n: int = 8) -> None:
    interesting = events[events["type"].isin(
        ["Goal", "Shot", "Substitution", "Foul Committed", "Pass"]
    )]
    sample = interesting.head(n)
    print(f"  (이벤트 DataFrame 앞쪽 {n}줄 샘플 — 컬럼 구조 확인용)\n")
    cols = ["period", "minute", "second", "team", "player", "type"]
    extra = [c for c in ["shot_outcome", "pass_outcome"] if c in sample.columns]
    print(sample[cols + extra].to_string(index=False))


def main() -> None:
    section("1. 무료 오픈 데이터 — FIFA 월드컵 시즌")
    comps = sb.competitions()
    wc = comps[
        (comps["competition_name"] == "FIFA World Cup")
        & (comps["competition_id"] == COMPETITION_ID)
    ]
    print(wc[["competition_id", "season_id", "competition_name", "season_name"]].to_string(index=False))

    section("2. 2022 월드컵 결승전")
    matches = sb.matches(competition_id=COMPETITION_ID, season_id=SEASON_ID)
    final = matches[matches["competition_stage"] == "Final"].iloc[0]
    print_match_summary(final)

    match_id = final["match_id"]

    section("3. 경기 이벤트")
    events = sb.events(match_id=match_id)
    lineups = sb.lineups(match_id=match_id)
    short_names = build_short_names(lineups)

    print_event_summary(events)

    section("3-1. 득점 타임라인")
    print_goals(events, short_names)

    section("3-2. 이벤트 샘플 (한 줄이 경기 속 한 순간)")
    print_sample_events(events)

    section("4. 라인업")
    print("  반환 타입: dict (키 = 팀 이름, 값 = 선수 DataFrame)")
    print_lineups_from_events(events, lineups)

    section("5. 컬럼 구조 (DB 설계 참고용)")
    print(f"  경기(matches) 컬럼 수: {len(matches.columns)}")
    print(f"  이벤트(events) 컬럼 수: {len(events.columns)}")
    print(f"  라인업(lineups) 컬럼: {list(next(iter(lineups.values())).columns)}")


if __name__ == "__main__":
    main()
