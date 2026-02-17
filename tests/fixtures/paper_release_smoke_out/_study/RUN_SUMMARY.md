# Run summary

## What was run
- **Task**: insider_key_misuse
- **Episodes per condition**: 2
- **Conditions**: 2
- **Study spec**: `C:\Users\mateo\LabTrust-Gym\tests\fixtures\paper_release_smoke_out\_study\study_spec_taskf_strict_signatures.yaml`
- **Git commit**: `d8a110a1dd9f07ad85b9bd527ae15be8b6ef1de1`

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
