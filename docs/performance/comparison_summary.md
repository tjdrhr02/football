# EXPLAIN ANALYZE — index before/after

Captured by `scripts/run_explain_benchmark.py`. Use the `.txt` files for screenshots (Seq Scan vs Index Scan lines + Execution Time).

| Benchmark | Before (no index) | After (indexes) | After w/o cover | Speedup |
|-----------|-------------------|-----------------|-------------------|---------|
| ETL: per-player pass/shot counts for one match (events) | Seq Scan, 130.500 ms | Index Scan, 0.905 ms | Index Scan, 1.067 ms | 144.2x |
| Korea campaign — defensive totals by match (fact) | Seq Scan, 0.242 ms | Index Scan, 0.025 ms | Index Scan, 0.040 ms | 9.7x |
| Player match stats — covering columns only (fact) | Index Scan, 0.057 ms | Index Only Scan, 0.024 ms | Index Scan, 0.012 ms | 2.4x |
| Korea formation timeline (team_match_formation) | Seq Scan, 0.026 ms | Seq Scan, 0.012 ms | Seq Scan, 0.015 ms | 2.2x |

## Screenshot checklist

1. **Seq Scan** — `before_events_match_pass_agg.txt` (Execution Time line visible)
2. **Index Scan** — `after_events_match_pass_agg.txt`
3. **Execution Time comparison** — this table or side-by-side `.txt` headers

## Covering index

Compare `after_no_cover_fact_cover_player_stats.txt` (heap Index Scan) vs `after_fact_cover_player_stats.txt` (Index Only Scan on `idx_fpms_cover`).
