# SOTA leaderboard (coordination)

Per-method means over all cells (scale x injection).

Run metadata: seed_base=100, git_sha=7563446fff1e (when available).

Source: pack_summary.csv. This run includes an application_phase dimension.

| method_id | throughput_mean | throughput_std | violations_mean | blocks_mean | resilience_score_mean | resilience_score_std | p95_tat_mean | on_time_rate_mean | critical_compliance_mean | attack_success_rate_mean | stealth_success_rate_mean | n_cells |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kernel_auction_whca_shielded | 0.0000 | 0.0000 | 107.08 | 257.00 | 0.6520 | 0.3741 | — | — | — | 0.0000 | 0.0000 | 12 |
| llm_detector_throttle_advisor | 0.0000 | 0.0000 | 13617.92 | 36583.00 | 0.1274 | 0.1608 | — | — | — | 0.0000 | 0.0000 | 12 |
| llm_local_decider_signed_bus | 0.0000 | 0.0000 | 13500.00 | 36300.00 | 0.5000 | 0.5222 | — | — | — | 0.0000 | 0.0000 | 12 |
| llm_repair_over_kernel_whca | 0.0000 | 0.0000 | 13500.00 | 36300.00 | 0.5000 | 0.5222 | — | — | — | 0.0000 | 0.0000 | 12 |

Key hospital-lab metrics: throughput (releases/episode), p95_tat (s), on_time_rate (SLA), critical_compliance (notify/ack), violations, blocks, resilience, attack_success_rate. See docs/benchmarks/hospital_lab_metrics.md in the repository.

**Note (throughput_mean = 0):** Throughput is the mean number of specimen releases (RELEASE_RESULT) per episode; higher is better. When all methods show 0, no coordination cell produced any releases. Common causes: (1) coord_risk pack cells use 1 episode per cell and coordination methods may not yet assign work that completes the accept -> process -> release pipeline in that horizon; (2) kernel allocators can report num_assignments = 0 (no alloc_emits); (3) LLM methods may error or return no valid release actions. For throughput comparison, run the throughput_sla task with scripted or kernel baselines; see coordination_benchmark_card.md.