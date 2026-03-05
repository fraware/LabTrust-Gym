# Hospital lab key metrics

This document lists the metrics that matter most for hospital lab (blood sciences lane) operations and where they are reported in LabTrust-Gym. Use it to ensure runs are evaluated on the right signals and to interpret pack and study outputs.

## Key metrics (what to report)

| Metric | Meaning | Direction | Where reported |
|--------|---------|------------|----------------|
| **Throughput** | Specimens completed (RELEASE_RESULT) per episode | Higher better | results JSON `episodes[].metrics.throughput`; pack_summary.csv `perf.throughput`; SOTA leaderboard `throughput_mean` |
| **Turnaround time (p95 TAT)** | 95th percentile accept-to-release time (seconds) | Lower better | results JSON `p95_turnaround_s`; summary_coord.csv / pack_summary.csv `perf.p95_tat`; SOTA leaderboard `p95_tat_mean` |
| **On-time rate** | Fraction of results released within SLA window | Higher better | results JSON `on_time_rate`; pack_summary.csv `perf.on_time_rate`; SOTA leaderboard `on_time_rate_mean` |
| **Critical result compliance** | Fraction of critical results with required notify/ack | Higher better | results JSON `critical_communication_compliance_rate`; pack_summary.csv `safety.critical_communication_compliance_rate`; SOTA leaderboard `critical_compliance_mean` |
| **Violations** | Invariant violations (safety) | Lower better; zero target | results JSON `violations_by_invariant_id`; pack_summary.csv `safety.violations_total`; SOTA leaderboard `violations_mean` |
| **Blocks** | Blocked actions (RBAC, signature, etc.) | Lower better | results JSON `blocked_by_reason_code`; pack_summary.csv `safety.blocks_total`; SOTA leaderboard (main) `blocks_mean`; method-class comparison `blocks_mean` |
| **Resilience score** | Composite (perf + safety + security + coordination) | Higher better | summary_coord.csv / pack_summary.csv `robustness.resilience_score`; SOTA leaderboard `resilience_score_mean` |
| **Attack success rate** | Fraction of episodes where injected attack succeeded | Lower better | pack_summary.csv `sec.attack_success_rate`; SOTA leaderboard (main) `attack_success_rate_mean`; method-class comparison `attack_success_rate_mean`; SECURITY/coordination_risk_matrix |
| **Detection / containment** | Steps to first detection and containment (security) | Lower better | pack_summary.csv `sec.detection_latency_steps`, `sec.containment_time_steps`; SOTA leaderboard (full) |

## Where each output lives

### Per-episode and cell-level

- **Per-episode**: Each `baselines/results/<task>_*.json` has `episodes[].metrics` with throughput, p50/p95_turnaround_s, on_time_rate, critical_communication_compliance_rate, violations_by_invariant_id, blocked_by_reason_code. See [Metrics contract](../contracts/metrics_contract.md).
- **Pack summary**: `coordination_pack/pack_summary.csv` (or pack root `pack_summary.csv`) has one row per cell (method, scale, injection); columns include the metrics above when produced by the coordination security pack. This CSV is the input to the summarizer that produces the SOTA leaderboards and method-class comparison.

### SOTA leaderboard (main)

- **Paths**: `summary/sota_leaderboard.md`, `summary/sota_leaderboard.csv`.
- **Purpose**: Single scannable table (~12 columns) with the most important per-method aggregates for hospital labs.
- **Columns**: method_id, throughput_mean, throughput_std, violations_mean, blocks_mean, resilience_score_mean, resilience_score_std, p95_tat_mean, on_time_rate_mean, critical_compliance_mean, attack_success_rate_mean, stealth_success_rate_mean, n_cells.
- **Uncertainty**: throughput_std and resilience_score_std are sample standard deviations over cells (reported when two or more cells exist per method); use them to interpret spread around the mean.
- **Run metadata**: When `pack_manifest.json` exists in the run directory (or its parent), the main leaderboard Markdown includes a **Run metadata** line at the top with seed_base and git_sha so the report is auditable and reproducible.

### SOTA leaderboard (full)

- **Paths**: `summary/sota_leaderboard_full.md`, `summary/sota_leaderboard_full.csv`.
- **Purpose**: All aggregated numeric metrics per method; use for detailed analysis when the main table is insufficient.
- **Content**: Every numeric column present in the source CSV (pack_summary.csv or summary_coord.csv) is aggregated: security (detection_latency_steps_mean, containment_time_steps_mean, etc.), and when the source is summary_coord.csv also comm (msg_count, p95_latency_ms, drop_rate), coordination (stale_action_rate, etc.), and LLM economics (tokens_per_step_mean, cost_total_tokens_sum, cost_estimated_cost_usd_sum, llm.error_rate_mean, etc.). Cost fields use **sum**; all others use **mean**. Column set depends on the data source.

### When to use main vs full table

- **Main table**: Day-to-day comparison of methods (throughput, safety, security headline, resilience, TAT/on-time/critical when available). Prefer this for stakeholder summaries and the UI portal’s primary leaderboard view.
- **Full table**: Deep dives, LLM cost/latency analysis, detection/containment timing, and when you need every metric that was collected in the run.

### Method-class comparison

- **Paths**: `summary/method_class_comparison.md`, `summary/method_class_comparison.csv`.
- **Purpose**: Aggregate by coordination class (e.g. kernel_schedulers, centralized, ripple, auctions, llm) instead of by method_id.
- **Columns**: method_class, throughput_mean, violations_mean, blocks_mean, resilience_score_mean, attack_success_rate_mean, stealth_success_rate_mean, n_cells. Aligned with the main SOTA table so safety and security metrics (blocks, attack_success_rate) are available at class level.

### Lab report

- **LAB_COORDINATION_REPORT.md**: Summarizes gate result and points to pack_gate.md and SECURITY/coordination_risk_matrix for security; for performance and safety at a glance, use the SOTA leaderboard and pack_summary.csv.

## Quick reference: artifact paths

| Artifact | Path(s) | Produced by |
|----------|---------|-------------|
| Pack summary (cell-level) | pack_summary.csv, coordination_pack/pack_summary.csv | run-coordination-security-pack, run-official-pack --include-coordination-pack |
| SOTA leaderboard (main) | summary/sota_leaderboard.md, summary/sota_leaderboard.csv | summarize-coordination, build-lab-coordination-report |
| SOTA leaderboard (full) | summary/sota_leaderboard_full.md, summary/sota_leaderboard_full.csv | summarize-coordination, build-lab-coordination-report |
| Method-class comparison | summary/method_class_comparison.md, summary/method_class_comparison.csv | summarize-coordination, build-lab-coordination-report |
| Run metadata (in main MD) | seed_base, git_sha in sota_leaderboard.md header | When pack_manifest.json exists in run dir |

## Throughput vs coordination pack

For **throughput** as the main signal (e.g. comparing methods on specimen completion rate), use the **throughput_sla** task and scripted or kernel baselines; see [Throughput comparison](throughput_comparison.md). The coordination pack (coord_risk / coord_scale) emphasizes safety, security, and resilience under injections; its throughput can be zero when no releases occur in the short horizons used. For hospital labs, report both: throughput and on-time rate from throughput_sla when comparing capacity, and violations, blocks, and resilience from the coordination pack when comparing safety and robustness.

## See also

- [Metrics contract](../contracts/metrics_contract.md) – units, timing modes, aggregation rules.
- [Coordination benchmark card](../coordination/coordination_benchmark_card.md) – perf.throughput, perf.p95_tat, safety, security, resilience definitions and SOTA report artifacts.
- [UI data contract](../contracts/ui_data_contract.md) – coordination_artifacts in the ui-export bundle (main and full leaderboard, method-class comparison).
