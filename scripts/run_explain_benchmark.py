"""Capture EXPLAIN (ANALYZE, BUFFERS) before/after performance indexes.

Workflow (matches AGENTS.md Step 4):
  1. --phase before       — drop §6 indexes, run benchmarks → Seq Scan captures
  2. --phase after_no_cover — apply indexes, drop only idx_fpms_cover, rerun cover benchmark
  3. --phase after        — apply full 03_indexes.sql (incl. covering), run all benchmarks

  --phase all runs the three steps above and writes comparison_summary.md.
  On failure during --phase all, indexes are re-applied in finally so PG is not left bare.

Outputs land in docs/performance/ for screenshot / portfolio use.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from football.config import KOREA_TEAM_ID, PROJECT_ROOT, SCHEMA_DIR
from football.db.connection import get_connection

SCHEMA_INDEXES = SCHEMA_DIR / "03_indexes.sql"
OUT_DIR = PROJECT_ROOT / "docs" / "performance"

PERF_INDEXES = [
    "idx_fpms_player_match",
    "idx_fpms_team_match",
    "idx_fpms_cover",
    "idx_events_match_type_player",
    "idx_tmf_timeline",
]

# Korea vs Brazil 16R — ETL index target match
BENCHMARK_MATCH_ID = 3869253  # Korea vs Brazil, Round of 16
SAMPLE_PLAYER_ID = 3083
SAMPLE_MATCH_ID = 3857262


@dataclass(frozen=True)
class Benchmark:
    key: str
    title: str
    sql: str
    notes: str = ""


BENCHMARKS = [
    Benchmark(
        key="events_match_pass_agg",
        title="ETL: per-player pass/shot counts for one match (events)",
        notes="Primary demo: Seq Scan → Index Scan on idx_events_match_type_player",
        sql="""
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    e.player_id,
    COUNT(*) FILTER (WHERE e.type = 'Pass') AS passes_attempted,
    COUNT(*) FILTER (WHERE e.type = 'Pass' AND e.outcome IS NULL) AS passes_completed,
    COUNT(*) FILTER (WHERE e.type = 'Shot') AS shots
FROM staging.events e
WHERE e.match_id = %(match_id)s
  AND e.player_id IS NOT NULL
GROUP BY e.player_id
""",
    ),
    Benchmark(
        key="fact_team_match_defense",
        title="Korea campaign — defensive totals by match (fact)",
        notes="idx_fpms_team_match: team_id filter across ~60 rows",
        sql="""
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    f.match_id,
    SUM(f.tackles)::int AS tackles,
    SUM(f.interceptions)::int AS interceptions,
    SUM(f.pressures)::int AS pressures,
    SUM(f.blocks)::int AS blocks
FROM analytics.fact_player_match_stats f
WHERE f.team_id = %(team_id)s
GROUP BY f.match_id
ORDER BY f.match_id
""",
    ),
    Benchmark(
        key="fact_cover_player_stats",
        title="Player match stats — covering columns only (fact)",
        notes="idx_fpms_cover: Index Only Scan when INCLUDE columns satisfy query",
        sql="""
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    f.xg,
    f.passes_attempted,
    f.passes_completed,
    f.pass_completion_rate,
    f.minutes_played
FROM analytics.fact_player_match_stats f
WHERE f.player_id = %(player_id)s
""",
    ),
    Benchmark(
        key="formation_timeline",
        title="Korea formation timeline (team_match_formation)",
        notes="idx_tmf_timeline: match_id + team_id + from_minute",
        sql="""
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT formation_code, from_minute, to_minute
FROM analytics.team_match_formation
WHERE match_id = %(match_id)s AND team_id = %(team_id)s
ORDER BY from_minute
""",
    ),
]


def drop_perf_indexes(cur) -> None:
    for name in PERF_INDEXES:
        cur.execute(f"DROP INDEX IF EXISTS analytics.{name}")
        cur.execute(f"DROP INDEX IF EXISTS staging.{name}")


def apply_indexes(cur) -> None:
    sql = SCHEMA_INDEXES.read_text(encoding="utf-8")
    cur.execute(sql)


def drop_cover_index(cur) -> None:
    cur.execute("DROP INDEX IF EXISTS analytics.idx_fpms_cover")


def explain_params() -> dict:
    return {
        "match_id": BENCHMARK_MATCH_ID,
        "team_id": KOREA_TEAM_ID,
        "player_id": SAMPLE_PLAYER_ID,
    }


def run_explain(cur, sql: str, params: dict) -> str:
    cur.execute("SET max_parallel_workers_per_gather = 0")
    cur.execute(sql, params)
    return "\n".join(row[0] for row in cur.fetchall())


def parse_plan_metrics(plan: str) -> dict:
    scan_types = []
    if "Seq Scan" in plan:
        scan_types.append("Seq Scan")
    if "Index Only Scan" in plan:
        scan_types.append("Index Only Scan")
    elif "Index Scan" in plan:
        scan_types.append("Index Scan")
    elif "Bitmap Index Scan" in plan:
        scan_types.append("Bitmap Index Scan")

    exec_match = re.search(r"Execution Time:\s*([\d.]+)\s*ms", plan)
    planning_match = re.search(r"Planning Time:\s*([\d.]+)\s*ms", plan)

    index_name = None
    idx_match = re.search(
        r"(?:Index (?:Only )?Scan using|Bitmap Index Scan on) (\w+)",
        plan,
    )
    if idx_match:
        index_name = idx_match.group(1)

    return {
        "scan_types": scan_types or ["(none detected)"],
        "execution_ms": float(exec_match.group(1)) if exec_match else None,
        "planning_ms": float(planning_match.group(1)) if planning_match else None,
        "index_name": index_name,
    }


def write_capture(phase: str, bench: Benchmark, plan: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    metrics = parse_plan_metrics(plan)
    path = OUT_DIR / f"{phase}_{bench.key}.txt"
    header = [
        f"# {bench.title}",
        f"# phase: {phase}",
        f"# captured: {datetime.now(timezone.utc).isoformat()}",
        f"# notes: {bench.notes}",
        f"# scan: {', '.join(metrics['scan_types'])}",
        f"# index: {metrics['index_name'] or '—'}",
        f"# planning_ms: {metrics['planning_ms']}",
        f"# execution_ms: {metrics['execution_ms']}",
        "",
    ]
    path.write_text("\n".join(header) + plan + "\n", encoding="utf-8")
    return path


def run_phase(phase: str, conn) -> list[dict]:
    cur = conn.cursor()
    rows = []
    params = explain_params()

    if phase == "before":
        drop_perf_indexes(cur)
        conn.commit()
    elif phase == "after":
        apply_indexes(cur)
        conn.commit()
    elif phase == "after_no_cover":
        apply_indexes(cur)
        drop_cover_index(cur)
        conn.commit()
    else:
        raise ValueError(f"unknown phase: {phase}")

    for bench in BENCHMARKS:
        plan = run_explain(cur, bench.sql, params)
        path = write_capture(phase, bench, plan)
        metrics = parse_plan_metrics(plan)
        rows.append(
            {
                "phase": phase,
                "key": bench.key,
                "file": str(path.relative_to(PROJECT_ROOT)),
                **metrics,
            }
        )
        print(
            f"[{phase}] {bench.key}: "
            f"{metrics['scan_types']} execution={metrics['execution_ms']}ms → {path.name}"
        )
    return rows


def write_summary(all_rows: list[dict]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "comparison_summary.md"

    by_key: dict[str, list[dict]] = {}
    for row in all_rows:
        by_key.setdefault(row["key"], []).append(row)

    lines = [
        "# EXPLAIN ANALYZE — index before/after",
        "",
        "Captured by `scripts/run_explain_benchmark.py`. "
        "Use the `.txt` files for screenshots (Seq Scan vs Index Scan lines + Execution Time).",
        "",
        "| Benchmark | Before (no index) | After (indexes) | After w/o cover | Speedup |",
        "|-----------|-------------------|-----------------|-------------------|---------|",
    ]

    for key, phase_rows in by_key.items():
        pmap = {r["phase"]: r for r in phase_rows}
        before = pmap.get("before", {})
        after = pmap.get("after", {})
        no_cover = pmap.get("after_no_cover", {})

        def fmt(r: dict) -> str:
            if not r:
                return "—"
            scan = r["scan_types"][0] if r.get("scan_types") else "?"
            ms = r.get("execution_ms")
            return f"{scan}, {ms:.3f} ms" if ms is not None else scan

        b_ms = before.get("execution_ms")
        a_ms = after.get("execution_ms")
        speedup = ""
        if b_ms and a_ms and a_ms > 0:
            speedup = f"{b_ms / a_ms:.1f}x"

        title = BENCHMARKS[next(i for i, b in enumerate(BENCHMARKS) if b.key == key)].title
        lines.append(
            f"| {title} | {fmt(before)} | {fmt(after)} | {fmt(no_cover)} | {speedup} |"
        )

    lines.extend(
        [
            "",
            "## Screenshot checklist",
            "",
            "1. **Seq Scan** — `before_events_match_pass_agg.txt` (Execution Time line visible)",
            "2. **Index Scan** — `after_events_match_pass_agg.txt`",
            "3. **Execution Time comparison** — this table or side-by-side `.txt` headers",
            "",
            "## Covering index",
            "",
            "Compare `after_no_cover_fact_cover_player_stats.txt` (Bitmap Heap Scan + "
            "`idx_fpms_player_match`) vs `after_fact_cover_player_stats.txt` "
            "(Index Only Scan on `idx_fpms_cover`, `Heap Fetches: 0`).",
            "",
            "## Notes",
            "",
            "- **events** (~235k rows): largest win — ETL `match_id` filter uses "
            "`idx_events_match_type_player`.",
            "- **fact team_id**: modest win on ~2k rows; still shows Seq Scan → Index Scan.",
            "- **formation** (~218 rows): planner keeps Seq Scan; PK already matches "
            "`(match_id, team_id, from_minute)`.",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[summary] {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="EXPLAIN ANALYZE before/after performance indexes")
    parser.add_argument(
        "--phase",
        choices=["before", "after", "after_no_cover", "all"],
        default="all",
        help="before=drop indexes; after=apply 03_indexes.sql; after_no_cover=indexes minus cover",
    )
    args = parser.parse_args()

    if not SCHEMA_INDEXES.is_file():
        print(f"[error] missing {SCHEMA_INDEXES}", file=sys.stderr)
        return 1

    conn = get_connection()
    all_rows: list[dict] = []
    restore_indexes = args.phase == "all"

    try:
        phases = (
            ["before", "after_no_cover", "after"]
            if args.phase == "all"
            else [args.phase]
        )
        for phase in phases:
            all_rows.extend(run_phase(phase, conn))
        if args.phase == "all":
            write_summary(all_rows)
    except Exception:
        if restore_indexes:
            cur = conn.cursor()
            apply_indexes(cur)
            conn.commit()
        raise
    finally:
        if restore_indexes:
            cur = conn.cursor()
            apply_indexes(cur)
            conn.commit()
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
