# Run report: figures and data tables

## Run context
- **Task**: TaskA
- **Conditions**: 4 (cond_0, cond_1, cond_2, cond_3)
- **Episodes per condition**: 1
- **Total episodes**: 4
- **Output directory**: `C:\Users\mateo\LabTrust-Gym\runs\trust_ablations_smoke`

## Metric definitions
- **throughput_mean**: Mean number of specimens released (RELEASE_RESULT) per episode. Higher is better.
- **violations_total**: Sum of invariant violations across episodes (by invariant_id). Lower is better.
- **p95_tat_mean**: Mean 95th percentile turnaround time (accept to release) in seconds. Lower is better when comparing conditions.
- **trust_cost_mean**: Mean (tokens_consumed + tokens_minted) per episode. Proxy for trust/override usage.
- **critical_compliance_mean**: Fraction of critical results with required notify/ack. Higher is better.
- **blocked_by_reason_code**: Count of actions blocked by policy (e.g. RBAC, QC_FAIL_ACTIVE).

## Figures
- `throughput_vs_violations.png` / `.svg`: Pareto view; prefer high throughput, low violations.
- `trust_cost_vs_p95_tat.png` / `.svg`: Trust cost vs turnaround; trade-off by condition.
- `violations_by_invariant_id.png` / `.svg`: Which invariants were violated (aggregate).
- `blocked_by_reason_code_top10.png` / `.svg`: Top reason codes for blocked actions.
- `critical_compliance_by_condition.png` / `.svg`: Critical communication compliance per condition.

## Data tables (figures/data_tables/)
- `summary.csv`, `paper_table.md`: Per-condition aggregates (paper-ready).
- `throughput_vs_violations.csv`, `trust_cost_vs_p95_tat.csv`: Underlying data for scatter plots.
- `violations_by_invariant_id.csv`, `blocked_by_reason_code_top10.csv`: Underlying data for bar charts.

## Data summary
- **Throughput**: All conditions had 0 releases. No RELEASE_RESULT was recorded in any episode.
  This usually means: (1) scripted baseline did not complete any run (e.g. reagent stockout, zone violations),
  or (2) episodes were too short, or (3) specimens were not accepted/queued. Check `policy_root` and
  `reagent_initial_stock` in initial_state, and that specimens start as accepted for study tasks.

- **Violations**: No invariant violations recorded.
