# Benchmark summary

Aggregated results (mean and std) per task and baseline. Schema: results.v0.2.

---

## Metric reference

| Metric | Description |
|--------|-------------|
| **task** | Task id (e.g. throughput_sla, multi_site_stat). |
| **agent_baseline_id** | Baseline or agent ID (e.g. scripted_ops_v1). |
| **partner_id** | Partner overlay if used; empty otherwise. |
| **n_episodes** | Number of episodes aggregated. |
| **throughput_mean** | Mean specimens released per episode (higher is better). |
| **throughput_std** | Std dev of throughput. |
| **p50_turnaround_s_mean** | Mean 50th percentile accept-to-release (s). |
| **p95_turnaround_s_mean** | Mean 95th percentile turnaround (s); lower is better for SLA. |
| **on_time_rate_mean** | Fraction released within SLA window. |
| **violations_total_mean** | Mean total invariant violations per episode (lower is better). |
| **critical_communication_compliance_rate_mean** | Fraction of critical results with required notify/ack. |

---

## Results

| agent_baseline_id | comm_drop_rate_mean | comm_drop_rate_std | comm_msg_count_mean | comm_msg_count_std | comm_p95_latency_ms_mean | comm_p95_latency_ms_std | containment_success_mean | containment_success_std | critical_communication_compliance_rate_mean | critical_communication_compliance_rate_std | detection_latency_s_mean | detection_latency_s_std | forensic_quality_score_mean | forensic_quality_score_std | fraction_of_attacks_contained_mean | fraction_of_attacks_contained_std | n_episodes | on_time_rate_mean | on_time_rate_std | p50_turnaround_s_mean | p50_turnaround_s_std | p95_turnaround_s_mean | p95_turnaround_s_std | partner_id | task | throughput_mean | throughput_std | time_to_first_detected_security_violation_mean | time_to_first_detected_security_violation_std | violations_total_mean | violations_total_std |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| scripted_ops_v1 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 8 |  |  |  |  |  |  |  | qc_cascade | 0 | 0 |  |  | 67.5 | 3.742 |
| scripted_ops_v1 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 8 |  |  |  |  |  |  |  | throughput_sla | 0 | 0 |  |  | 71 | 0 |

---

## Run info

| agent_baseline_id | episodes_per_second | n_episodes | partner_id | run_duration_wall_s | task |
| :--- | :--- | ---: | :--- | :--- | :--- |
| scripted_ops_v1 |  | 2 |  | 0 | qc_cascade |
| scripted_ops_v1 |  | 2 |  | 0 | qc_cascade |
| scripted_ops_v1 |  | 2 |  | 0 | qc_cascade |
| scripted_ops_v1 |  | 2 |  | 0 | qc_cascade |
| scripted_ops_v1 |  | 2 |  | 0 | throughput_sla |
| scripted_ops_v1 |  | 2 |  | 0 | throughput_sla |
| scripted_ops_v1 |  | 2 |  | 0 | throughput_sla |
| scripted_ops_v1 |  | 2 |  | 0 | throughput_sla |


---

*Summary generated from results.v0.2.*
