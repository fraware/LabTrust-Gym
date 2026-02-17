# Coordination studies

This document describes how to run the policy-driven coordination study and how to interpret the Pareto front report. For LLM-based coordination (pipeline modes, proposal schema, shield and repair, security evaluation, reporting), see [LLM Coordination Protocol](../benchmarks/llm_coordination_protocol.md). External reviewers can run with `--llm-backend deterministic` (no network), then verify bundles and review coverage gates offline.

**External reviewer automation**: Run `scripts/run_external_reviewer_checks.sh [out_dir] [spec_path]` to execute the coordination study (deterministic), validate `summary/summary_coord.csv` and required columns, run a **coverage gate** (every `required_bench: true` (method_id, risk_id) cell from the method-risk matrix must have at least one row in the summary; by default missing cells are reported and the script continues; set `LABTRUST_STRICT_COVERAGE=1` to exit 1 when any required cell is missing), optionally run `verify-bundle` on the first EvidenceBundle, and ensure or generate `COORDINATION_LLM_CARD.md`. See [LLM Coordination Protocol](../benchmarks/llm_coordination_protocol.md) and [CI](../operations/ci.md) for the optional CI job (`LABTRUST_EXTERNAL_REVIEWER_CHECKS=1`). On Windows, run the script under WSL or ensure shell scripts use LF line endings (`.gitattributes` sets `*.sh text eol=lf`).

## Overview

The coordination study runner executes a deterministic experiment matrix: for each cell **(scale x method x injection)** it runs a fixed number of episodes (coord_risk), writes per-cell results in the existing results v0.2 format (with optional `coordination` and `security` blocks), then aggregates a summary CSV and a Pareto front report. A separate **internal regression pack** (fixed matrix, 1 ep/cell, gate thresholds) is run with `labtrust run-coordination-security-pack --out <dir>`; see [Security attack suite – Coordination security pack](../risk-and-security/security_attack_suite.md#coordination-security-pack-internal-regression). For **hospital lab**: run the pack (optionally with `--matrix-preset hospital_lab`), then `labtrust build-lab-coordination-report --pack-dir <dir>` to get SOTA leaderboard, coordination decision, and `LAB_COORDINATION_REPORT.md`; see [Lab coordination report](lab_coordination_report.md).

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

With **`LABTRUST_REPRO_SMOKE=1`** in the environment, episodes per cell are capped to 1 for fast smoke runs. The study spec may include both **INJ-*** injection IDs (full injectors from `policy/coordination/injections.v0.2.yaml`) and **legacy/reserved** IDs (e.g. `inj_tool_selection_noise`, `inj_prompt_injection`, `none`). Legacy and reserved IDs are **out of scope for this release**: they use a passthrough NoOpInjector so all cells run without error, but no fault is actually injected. For active injections use INJ-* IDs. The full list of reserved no-op IDs is documented in [Risk register – Reserved and legacy injection IDs](../risk-and-security/risk_register.md#reserved-and-legacy-injection-ids-out-of-scope-for-this-release).

### LLM-only with live backends

To run all coordination methods as **LLM-based, multi-agent, with live backends** (OpenAI, Ollama, or Anthropic), use the dedicated LLM-only spec and set `--llm-backend`:

```bash
labtrust run-coordination-study --spec policy/coordination/coordination_study_spec_llm_live.v0.1.yaml --out <dir> --llm-backend openai_live
```

Or with Ollama or Anthropic:

```bash
labtrust run-coordination-study --spec policy/coordination/coordination_study_spec_llm_live.v0.1.yaml --out <dir> --llm-backend ollama_live
labtrust run-coordination-study --spec policy/coordination/coordination_study_spec_llm_live.v0.1.yaml --out <dir> --llm-backend anthropic_live
```

Use `--allow-network` or set `LABTRUST_ALLOW_NETWORK=1` and provide the appropriate API keys (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) in the environment or `.env`. Token usage and latency depend on the live backend; scale configs (e.g. `small_smoke`, `medium_stress_signed_bus`) are the same as for deterministic runs. See [Coordination methods audit](coordination_methods_audit.md) for which methods support live backends.

**LLM coordination protocol–targeted injections** (`policy/coordination/injections.v0.2.yaml`): `INJ-COORD-PROMPT-INJECT-001` (malicious instruction in coordination context; success = shield blocks or disallowed action), `INJ-COORD-PLAN-REPLAY-001` (replay of signed plan after epoch superseded; blocked by replay/epoch binding when enabled), `INJ-COORD-BID-SHILL-001` (auction bidder shilling; success = gini up + on_time down; stealth if no detection). Each is deterministic and mapped to `risk_registry.v0.1` and `method_risk_matrix.v0.1`. To run a single cell for one of these injections:

```bash
labtrust run-benchmark --task coord_risk --episodes 1 --seed 42 --out results.json --coord-method kernel_auction_whca_shielded --injection INJ-COORD-PROMPT-INJECT-001
```

Results include `sec.attack_success_rate`, `sec.stealth_success_rate`, `sec.blast_radius_proxy`. Unit and integration tests: `tests/test_coord_protocol_injections.py`.

### Coverage integrity gate (preflight)

Before running cells, the study runner runs a **coverage preflight**: for every `(method_id, risk_id)` cell with `required_bench: true` in the method-risk matrix, at least one injection in the spec must cover that risk (via `policy/coordination/risk_to_injection_map.v0.1.yaml` or `risk_registry.suggested_injections`), or the risk must be listed in the spec under **waived_risks** with a reason. If any required risk has no covering injection and is not waived:

- **Non-strict** (default): the runner writes `summary/coverage_missing.json` (missing risk_ids, covering_injection_ids, message) and continues.
- **Strict** (`LABTRUST_STRICT_COVERAGE=1`): the runner exits with code 1 and a clear message; no cells are run.

Run the gate locally (non-strict, study runs and writes `coverage_missing.json` if needed):

```bash
labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out runs/coord_out
```

Strict mode (fail fast when coverage is missing):

```bash
LABTRUST_STRICT_COVERAGE=1 labtrust run-coordination-study --spec policy/coordination/coordination_study_spec.v0.1.yaml --out runs/coord_out
```

Tests: `tests/test_coverage_integrity_gate.py` (strict mode fails when a required risk has no injection; non-strict writes deterministic `coverage_missing.json`).

## Spec format

The spec YAML must include:

- **study_id**: Identifier for the run.
- **seed_base**: Base seed; cell seeds are deterministic (seed_base + scale_idx * 10000 + method_idx * 100 + injection_idx).
- **episodes_per_cell**: Number of episodes per (scale, method, injection) cell.
- **scales**: List of `{ name, values }`; the Cartesian product defines scale rows. Names map to scale config (e.g. `num_agents`, `num_sites`, `num_devices`, `arrival_rate`, `horizon_steps`).
- **methods**: List of coordination method IDs (e.g. `centralized_planner`, `hierarchical_hub_rr`, `llm_constrained`).
- **risks**: Optional list of risk IDs (e.g. R-TOOL-001); used as labels in the summary.
- **injections**: List of `{ injection_id, intensity?, seed_offset? }` for the risk injection harness.
- **waived_risks**: Optional list of `{ risk_id, reason }` for required risks that are explicitly not covered (preflight then skips them).

## Output layout

```
<out>/
  manifest_coordination.json   # study_id, seed_base, cell_ids, pareto_dir, etc.
  cells/
    <scale_id>_<method_id>_<injection_id>/
      results.json              # v0.2 + optional coordination / security
      episodes.jsonl             # optional step log
  summary/
    summary_coord.csv            # one row per cell
    pareto.md                   # Pareto front and robust winner
    sota_leaderboard.csv        # per-method means (throughput_mean, violations_mean, resilience_score_mean, stealth_success_rate_mean)
    sota_leaderboard.md         # leaderboard markdown table
    method_class_comparison.csv # per-class means (centralized vs ripple vs evolving vs auctions vs kernel_schedulers)
    method_class_comparison.md  # method-class comparison markdown table
    coverage_missing.json        # written by preflight when required risks have no covering injection (non-strict)
  PARETO/                        # multi-objective evaluation (v0.1)
    pareto.json                  # nondominated fronts, per-method CIs (v0.3 extension)
    pareto.md                    # interpretation + fronts + CIs
    frontier.svg                 # canonical plot: throughput vs p95 TAT, front highlighted
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
| proposal_valid_rate, blocked_rate, repair_rate | Coordination validity and repair rates (LLM methods). |
| tokens_per_step, p95_llm_latency_ms | LLM tokens per step and p95 latency (null for non-LLM). |
| cost.total_tokens | Total LLM tokens over the cell (0 for non-LLM methods). |
| cost.estimated_cost_usd | Estimated LLM API cost in USD when model pricing exists (null otherwise). |
| llm.error_rate | Mean LLM call error rate over episodes (0 for deterministic). |
| llm.invalid_output_rate | Mean rate of schema violations / parse fallbacks (invalid outputs per call). |

## SOTA leaderboard and method-class comparison

The study runner (and the standalone `summarize-coordination` command) produces:

- **SOTA leaderboard**: One row per method with `throughput_mean`, `violations_mean`, `resilience_score_mean`, `stealth_success_rate_mean` (means over all cells for that method), plus `n_cells`. Written as `summary/sota_leaderboard.csv` and `summary/sota_leaderboard.md`.
- **Method-class comparison**: Same metrics aggregated by *method class* (centralized, ripple, evolving, auctions, kernel_schedulers, and optionally decentralized, swarm, llm, other). Written as `summary/method_class_comparison.csv` and `summary/method_class_comparison.md`.

To generate or refresh these from an existing run directory (e.g. after copying summary_coord.csv):

```bash
labtrust summarize-coordination --in <run_dir> --out <out_dir>
```

Input: `--in` must contain `summary/summary_coord.csv` or `summary_coord.csv`. Output: `--out` receives `summary/sota_leaderboard.csv`, `sota_leaderboard.md`, `method_class_comparison.csv`, `method_class_comparison.md`. You can use the same path for `--in` and `--out` to add the aggregation artifacts to an existing run.

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

## PARETO/ folder (multi-objective evaluation v0.1)

When the study run writes the PARETO directory, it contains paper-grade outputs that do not change results.v0.2 semantics (v0.3 extension for extra stats only).

**Objectives**  
Stable Pareto front over four objectives: **throughput** (maximize), **p95 TAT** (minimize), **violations** (minimize), **security success rate** (maximize; derived as 1 - attack_success_rate). A cell is *nondominated* if no other cell is strictly better on all four (with at least one strictly better).

**Per-method confidence intervals**  
For each method, 95% bootstrap confidence intervals are computed for mean throughput, p95 TAT, violations, and resilience score. Resampling is **deterministic** (seeded from the study `seed_base`), so the same study run yields identical CIs. Use CIs to compare methods: non-overlapping intervals suggest a significant difference; overlapping intervals do not imply no difference.

**Artifacts**  
- **pareto.json**: Machine-readable fronts per scale (`fronts_per_scale`), per-method CIs (`per_method_ci`), and objective list. Version field `pareto_version: "0.1"` and `version: "0.3"` for the extension.
- **pareto_cost.json**: Cost-aware Pareto front: same objectives plus **cost.total_tokens** (minimize). Separate file so the main front is unchanged.
- **pareto.md**: Human-readable summary: **Objectives (quick reference)** table at the top, nondominated front per scale, **Cost-aware Pareto front** section (objectives plus cost.total_tokens), and per-method CI table.
- **frontier.svg**: Canonical 2D plot of throughput vs p95 TAT; Pareto-front points are highlighted. Supports light (default) or dark theme when generated via the study runner.

**Determinism**  
Same `seed_base` and same summary rows (same cell results) produce identical PARETO content. Use a fixed `seed_base` in the spec for reproducible figures and tables.

## Generating figures

After running a coordination study, generate plots (resilience vs p95_tat scatter, attack success rate by method and injection):

```bash
labtrust make-plots --run <out_dir> [--theme light|dark]
```

This writes `figures/resilience_vs_p95_tat.png`, `figures/resilience_vs_p95_tat.svg`, `figures/attack_success_rate_by_method_injection.png`, and `.svg` under `<out_dir>`. Use `--theme dark` for dark-background figures. All study figures use a consistent palette and style (see [Studies and plots](../benchmarks/studies.md)).

## Determinism

With a fixed **seed_base** and the same spec, the runner produces the same cell seeds, so results and summaries are reproducible. Official regression or baselines should pin `seed_base` in the spec.
