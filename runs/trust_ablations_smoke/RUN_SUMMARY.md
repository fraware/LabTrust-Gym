# Run summary

## What was run
- **Task**: TaskA
- **Episodes per condition**: 1
- **Conditions**: 4
- **Study spec**: `C:\Users\mateo\LabTrust-Gym\policy\studies\trust_ablations.v0.1.yaml`
- **Git commit**: `f168410be388f50462178ea9e0defffd0483857b`

## Output layout
| Path | Description |
|------|-------------|
| `manifest.json` | Run metadata, condition_ids, seeds, git hash |
| `results/<cond_id>/results.json` | Per-condition benchmark results (episodes, metrics) |
| `logs/<cond_id>/episodes.jsonl` | Episode logs when logging enabled |
| `figures/` | PNG/SVG plots and `figures/data_tables/` (CSV, paper_table.md) |
| `figures/RUN_REPORT.md` | Metric definitions and how to interpret the figures |

## Next steps
1. Inspect `figures/RUN_REPORT.md` for metric definitions and data summary.
2. Open `figures/data_tables/summary.csv` or `paper_table.md` for per-condition aggregates.
3. If all throughputs are zero, see the "Data summary" section in `figures/RUN_REPORT.md` for troubleshooting.
