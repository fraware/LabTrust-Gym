# SOTA leaderboard (full metrics)

Per-method aggregates over all cells; columns depend on data source (pack_summary vs summary_coord).
When source is summary_coord.csv, comm/LLM/cost columns may be present.

| method_id | attack_success_rate_mean | blocks_total_mean | containment_time_steps_mean | detection_latency_steps_mean | resilience_score_mean | stealth_success_rate_mean | throughput_mean | time_to_attribution_steps_mean | violations_total_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kernel_auction_whca_shielded | 0.0000 | 257.0000 | 0.0000 | 0.0000 | 0.6520 | 0.0000 | 0.0000 | 0.0000 | 107.0833 |
| llm_detector_throttle_advisor | 0.0000 | 36583.0000 | 0.0000 | 2.6667 | 0.1274 | 0.0000 | 0.0000 | 2.6667 | 13617.9167 |
| llm_local_decider_signed_bus | 0.0000 | 36300.0000 | 0.0000 | 0.0000 | 0.5000 | 0.0000 | 0.0000 | 0.0000 | 13500.0000 |
| llm_repair_over_kernel_whca | 0.0000 | 36300.0000 | 0.0000 | 0.0000 | 0.5000 | 0.0000 | 0.0000 | 0.0000 | 13500.0000 |