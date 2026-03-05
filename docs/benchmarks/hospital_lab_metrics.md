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
| **Blocks** | Blocked actions (RBAC, signature, etc.) | Lower better | results JSON `blocked_by_reason_code`; pack_summary.csv `safety.blocks_total` |
| **Resilience score** | Composite (perf + safety + security + coordination) | Higher better | summary_coord.csv / pack_summary.csv `robustness.resilience_score`; SOTA leaderboard `resilience_score_mean` |
| **Attack success rate** | Fraction of episodes where injected attack succeeded | Lower better | pack_summary.csv `sec.attack_success_rate`; SECURITY/coordination_risk_matrix |
| **Detection / containment** | Steps to first detection and containment (security) | Lower better | pack_summary.csv `sec.detection_latency_steps`, `sec.containment_time_steps` |

## Where each output lives

- **Per-episode**: Each `baselines/results/<task>_*.json` has `episodes[].metrics` with throughput, p50/p95_turnaround_s, on_time_rate, critical_communication_compliance_rate, violations_by_invariant_id, blocked_by_reason_code. See [Metrics contract](../contracts/metrics_contract.md).
- **Pack summary**: `coordination_pack/pack_summary.csv` (or pack root `pack_summary.csv`) has one row per cell (method, scale, injection); columns include the metrics above when produced by the coordination security pack.
- **SOTA leaderboard**: `coordination_pack/summary/sota_leaderboard.md` (and `.csv`) aggregates per method: throughput_mean, violations_mean, resilience_score_mean, p95_tat_mean, on_time_rate_mean, critical_compliance_mean, stealth_success_rate_mean.
- **Lab report**: `LAB_COORDINATION_REPORT.md` summarizes gate result and points to pack_gate.md and SECURITY/coordination_risk_matrix for security; for performance and safety at a glance, use the SOTA leaderboard and pack_summary.csv.

## Throughput vs coordination pack

For **throughput** as the main signal (e.g. comparing methods on specimen completion rate), use the **throughput_sla** task and scripted or kernel baselines; see [Throughput comparison](throughput_comparison.md). The coordination pack (coord_risk / coord_scale) emphasizes safety, security, and resilience under injections; its throughput can be zero when no releases occur in the short horizons used. For hospital labs, report both: throughput and on-time rate from throughput_sla when comparing capacity, and violations, blocks, and resilience from the coordination pack when comparing safety and robustness.

## See also

- [Metrics contract](../contracts/metrics_contract.md) – units, timing modes, aggregation rules.
- [Coordination benchmark card](../coordination/coordination_benchmark_card.md) – perf.throughput, perf.p95_tat, safety, security, resilience definitions.
