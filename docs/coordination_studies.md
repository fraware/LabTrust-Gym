# Coordination studies

This document describes how to run the policy-driven coordination study and how to interpret the Pareto front report.

## Overview

The coordination study runner executes a deterministic experiment matrix: for each cell **(scale x method x injection)** it runs a fixed number of episodes (TaskH_COORD_RISK), writes per-cell results in the existing results v0.2 format (with optional `coordination` and `security` blocks), then aggregates a summary CSV and a Pareto front report.

## Running a study

From the repository root:

```bash
labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out <dir>
```

Example:

```bash
labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out runs/coord_20250101
```

- **`--spec`**: Path to the coordination study spec YAML (see below).
- **`--out`**: Output directory. The command creates:
  - `cells/<cell_id>/results.json` for each cell (v0.2 + optional `coordination` / `security`).
  - `summary/summary_coord.csv`: aggregated metrics per (method_id, scale_id, risk_id, injection_id).
  - `summary/pareto.md`: per-scale Pareto front and robust winner.

With **`LABTRUST_REPRO_SMOKE=1`** in the environment, episodes per cell are capped to 1 for fast smoke runs. The study spec may include both **INJ-*** injection IDs (full injectors) and **legacy** IDs (e.g. `inj_tool_selection_noise`); legacy IDs use a passthrough NoOpInjector so all cells run without error.

## Spec format

The spec YAML must include:

- **study_id**: Identifier for the run.
- **seed_base**: Base seed; cell seeds are deterministic (seed_base + scale_idx * 10000 + method_idx * 100 + injection_idx).
- **episodes_per_cell**: Number of episodes per (scale, method, injection) cell.
- **scales**: List of `{ name, values }`; the Cartesian product defines scale rows. Names map to scale config (e.g. `num_agents`, `num_sites`, `num_devices`, `arrival_rate`, `horizon_steps`).
- **methods**: List of coordination method IDs (e.g. `centralized_planner`, `hierarchical_hub_rr`, `llm_constrained`).
- **risks**: Optional list of risk IDs (e.g. R-TOOL-001); used as labels in the summary.
- **injections**: List of `{ injection_id, intensity?, seed_offset? }` for the risk injection harness.

## Output layout

```
<out>/
  manifest_coordination.json   # study_id, seed_base, cell_ids, etc.
  cells/
    <scale_id>_<method_id>_<injection_id>/
      results.json              # v0.2 + optional coordination / security
      episodes.jsonl             # optional step log
  summary/
    summary_coord.csv            # one row per cell
    pareto.md                   # Pareto front and robust winner
```

## Summary CSV columns

`summary/summary_coord.csv` includes:

| Column | Description |
|--------|-------------|
| method_id | Coordination method. |
| scale_id | Scale configuration id (from spec scales). |
| risk_id | Risk label (from spec risks or injection_id). |
| injection_id | Injected risk id (e.g. INJ-COMMS-POISON-001). |
| perf.throughput | Mean throughput over episodes. |
| perf.p95_tat | Mean p95 turnaround time (s). |
| safety.violations_total | Total invariant violations. |
| sec.attack_success_rate | Fraction of episodes where the attack succeeded. |
| sec.detection_latency_steps | Mean steps to first detection (when applicable). |
| sec.containment_time_steps | Mean steps to containment (when applicable). |
| robustness.resilience_score | Composite score (higher is better); from policy/coordination/resilience_scoring.v0.1.yaml. |
| resilience.component_perf, component_safety, component_security, component_coordination | Per-component scores used to compute resilience_score. |

## Interpreting the Pareto report

`summary/pareto.md` contains:

1. **Per-scale Pareto front**  
   For each scale, the report lists cells that are *non-dominated* with respect to:
   - Minimize **p95_tat**
   - Minimize **violations_total**
   - Maximize **resilience_score**  

   A cell is on the front if no other cell is strictly better on all three (with at least one strictly better).

2. **Robust winner under risk suite**  
   The method with the **highest mean resilience score** across all cells (all scales and injections) is reported. This highlights which coordination method tends to remain most resilient across the injected risk suite.

## Generating figures

After running a coordination study, generate plots (resilience vs p95_tat scatter, attack success rate by method and injection):

```bash
labtrust make-plots --run <out_dir>
```

This writes `figures/resilience_vs_p95_tat.png`, `figures/resilience_vs_p95_tat.svg`, `figures/attack_success_rate_by_method_injection.png`, and `.svg` under `<out_dir>`. Matplotlib default colors are used (no seaborn).

## Determinism

With a fixed **seed_base** and the same spec, the runner produces the same cell seeds, so results and summaries are reproducible. Official regression or baselines should pin `seed_base` in the spec.
