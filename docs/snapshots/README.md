# Analysis snapshots

JSON output from `football-analysis` (or `scripts/analysis.py`).

| File | Description |
|------|-------------|
| `analysis_results.json` | WC2022 exploratory queries (validation + 8 analysis blocks). Regenerate after pipeline or schema changes. |

```bash
football-analysis --competition-id 43 --season-id 106
```

Used as reference data for `canvases/analysis-story.canvas.tsx`.
