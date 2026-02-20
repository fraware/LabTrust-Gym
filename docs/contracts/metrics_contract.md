# Metrics contract

This document defines units, when each metric is meaningful (explicit vs simulated timing mode), and aggregation rules for benchmark results. Used by results.v0.2 (CI-stable) and results.v0.3 (paper-grade).

**Schema alignment:** The per-episode metrics table below is the source of truth for result fields. The JSON schema `policy/schemas/results.v0.2.schema.json` (and v0.3) should stay aligned with this table when adding or changing metrics.

**Pipeline and audit:** Result and summary files are pipeline-agnostic in schema (same metrics regardless of pipeline mode). Every benchmark result file records **pipeline_mode** (`deterministic` | `llm_offline` | `llm_live`), **llm_backend_id**, **allow_network**, and **non_deterministic** for audit. Deterministic runs are required for baseline regression and for the canonical official baselines under `benchmarks/baselines_official/v0.2/results/`.

## Timing modes

- **explicit**: Step timestamps only; no device completion times. p95 TAT is derived from step times. Device utilization and queue-length stats are not produced.
- **simulated**: Device capacity and service-time models apply; p95 TAT is meaningful (accept→release includes queuing and device time). Device utilization and queue-length metrics are populated.

## Per-episode metrics

| Metric | Unit | Meaningful when | Aggregation (summary) |
|--------|------|------------------|------------------------|
| **throughput** | count (integer) | Both | Mean, std; v0.3: quantiles (p50, p90), 95% CI |
| **p50_turnaround_s** | seconds | Both (explicit: step-derived; simulated: completion-derived) | Mean, std; v0.3: quantiles, 95% CI |
| **p95_turnaround_s** | seconds | Both; **simulated** preferred for interpretation | Mean, std; v0.3: quantiles, 95% CI |
| **p95_turnaround_s_note** | — | Informational | Not aggregated |
| **on_time_rate** | [0, 1] | Both (requires sla_turnaround_s) | Mean, std |
| **violations_by_invariant_id** | dict (invariant_id → count) | Both | Sum over episodes; per-invariant totals |
| **blocked_by_reason_code** | dict (reason_code → count) | Both | Sum over episodes; per-reason totals |
| **critical_communication_compliance_rate** | [0, 1] or null | Both | Mean over episodes with non-null |
| **tokens_minted** | count | Both | Sum or mean; v0.2 regression: integer only |
| **tokens_consumed** | count | Both | Sum or mean; v0.2 regression: integer only |
| **holds_count** | count | Both | Sum or mean; v0.2 regression: integer only |
| **steps** | count | Both | Mean, std; v0.2 regression: integer only |
| **transport_consignment_count** | count | Both (multi_site_stat) | Sum or mean |
| **transport_temp_excursions** | count | Both (multi_site_stat) | Sum or mean |
| **coc_breaks_count** | count | Both (multi_site_stat) | Sum or mean |
| **detection_latency_s** | seconds | adversarial_disruption | Mean over episodes with value |
| **containment_success** | boolean | adversarial_disruption | Fraction true (0 or 1 per episode) |
| **time_to_first_detected_security_violation** | seconds | insider_key_misuse | Mean over episodes with value |
| **fraction_of_attacks_contained** | [0, 1] | insider_key_misuse | Mean over episodes |
| **forensic_quality_score** | [0, 1] | insider_key_misuse | Mean over episodes |
| **device_utilization** | per-device [0, 1] | **Simulated only** | Mean over episodes (per device); v0.3 |
| **device_queue_length_mean** | per-device float | **Simulated only** | Mean over episodes; v0.3 |
| **device_queue_length_max** | per-device integer | **Simulated only** | Max over episodes; v0.3 |

## CI-stable subset (v0.2 regression)

For cross-OS/Python stability, the baseline regression guard compares only:

- **Integers**: throughput, holds_count, tokens_minted, tokens_consumed, steps
- **Structs**: blocked_by_reason_code, violations_by_invariant_id

Float metrics (p50_turnaround_s, p95_turnaround_s, on_time_rate, etc.) are **not** compared in the regression test so that small numerical differences do not fail CI.

## Paper-grade (v0.3)

v0.3 adds optional fields for reporting:

- **Quantiles**: turnaround_quantiles_s (p10, p25, p50, p75, p90); throughput/summary quantiles in aggregated summary.
- **Confidence intervals**: 95% CI (e.g. mean ± 1.96 * std/sqrt(n)) for throughput, p95_turnaround_s, etc., in summary.
- **Simulated-mode distributions**: device_utilization, device_queue_length_mean, device_queue_length_max per episode; aggregated in summary as mean/max over episodes.

Summary outputs (from `labtrust summarize-results --in <paths> --out <dir> --basename summary`):

- **summary_v0.2.csv** — CI-stable; backward compatible. Columns: task, agent_baseline_id, partner_id, n_episodes, plus for each metric only *_mean and *_std (e.g. throughput_mean, throughput_std, p95_turnaround_s_mean, p95_turnaround_s_std). No quantile or CI columns. Used for baseline regression guard.
- **summary_v0.3.csv** — Same rows as v0.2; columns include v0.2 columns plus paper-grade: *_p50, *_p90, *_mean_ci_lower, *_mean_ci_upper (when computable). May contain empty/NaN for quantiles or CI when insufficient episodes.
- **summary.csv** — Copy of summary_v0.2.csv (identical content).
- **summary.md** — Markdown table derived from v0.2 aggregates only (same columns as summary_v0.2.csv). No quantile or CI columns in the table. When any result has `metadata.run_duration_wall_s`, the markdown also includes a **Run info** section (table of run_duration_wall_s, episodes_per_second per result) and a short footer.

Schema compatibility: every v0.2 top-level field and every v0.2 episode.metrics field exists in v0.3 with compatible types; v0.3 may add optional fields. Enforced by `tests/test_metrics_contract.py`.

## Coordination LLM economics (results.v0.2)

For LLM-based coordination methods (planner, allocator, bidder, repairer, local-decider), each episode may include an optional **coordination.llm** block with consistent economics fields. When the method is non-LLM or no LLM was invoked, this block is absent; aggregation fills 0 or null for summary outputs.

| Field | Type | Meaning |
|-------|------|--------|
| **llm.call_count** | integer | Number of LLM calls in the episode (0 for deterministic unless simulated). |
| **llm.total_tokens** | integer | Total input + output tokens (0 for deterministic unless simulated). |
| **llm.tokens_per_step** | float | total_tokens / steps. |
| **llm.mean_latency_ms** | float or null | Mean latency per call in ms; null for offline/deterministic. |
| **llm.p95_latency_ms** | float or null | 95th percentile latency per call; null for offline. |
| **llm.error_rate** | float | Fraction of calls that failed (e.g. API errors). |
| **llm.invalid_output_rate** | float | Schema violations or parse fallbacks per call (invalid outputs / call_count). |
| **llm.estimated_cost_usd** | float or null | Estimated cost in USD when model pricing exists; null otherwise. |

Aggregation (e.g. coordination study summary): **cost.total_tokens** is the sum of episode `llm.total_tokens`; **cost.estimated_cost_usd** is the sum of episode `llm.estimated_cost_usd`; **llm.error_rate** and **llm.invalid_output_rate** are means over episodes. For cells with no coordination.llm in any episode, these summary fields are 0 or null.

## Run metadata (optional)

The benchmark runner writes optional fields under **metadata** for harness observability and environment fingerprinting (auditability for papers and release):

| Field | Type | Meaning |
|-------|------|--------|
| **metadata.run_duration_wall_s** | number | Wall-clock duration of the full run (all episodes) in seconds. |
| **metadata.run_duration_episodes_per_s** | number | Episodes per second (num_episodes / run_duration_wall_s). |
| **metadata.python_version** | string | Python version at run time (e.g. 3.11.0). |
| **metadata.platform** | string | Platform identifier (e.g. win32, linux). |

These do not affect reproducibility (seed + policy + git remain the source of truth). Used for performance regression and run comparison.

## Schema versions

- **results.v0.2**: Normative results JSON (task, seeds, episodes with metrics). No change to existing fields or semantics. Optional **coordination.llm** per episode as above.
- **results.v0.3**: Extends v0.2; same required fields; adds optional metrics (quantiles, ci_*, device_utilization, device_queue_length_*). Results JSON may be emitted as v0.2 (current) or v0.3 (when paper-grade fields are populated).
