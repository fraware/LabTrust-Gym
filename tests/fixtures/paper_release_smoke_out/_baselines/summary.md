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
| adversary_v1 |  |  |  |  |  |  |  |  |  |  | 0 | 0 |  |  |  |  | 1 |  |  |  |  |  |  |  | adversarial_disruption | 0 | 0 |  |  | 6 | 0 |
| scripted_ops_v1 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  |  |  |  |  |  | coord_risk | 0 | 0 |  |  | 0 | 0 |
| scripted_ops_v1 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  |  |  |  |  |  | coord_scale | 0 | 0 |  |  | 0 | 0 |
| insider_v1 |  |  |  |  |  |  |  |  |  |  | 0 | 0 | 1 | 0 | 1 | 0 | 1 |  |  |  |  |  |  |  | insider_key_misuse | 0 | 0 | 30 | 0 | 0 | 0 |
| scripted_ops_v1 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  |  |  |  |  |  | multi_site_stat | 0 | 0 |  |  | 0 | 0 |
| scripted_ops_v1 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  |  |  |  |  |  | qc_cascade | 0 | 0 |  |  | 71 | 0 |
| scripted_ops_v1 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  |  |  |  |  |  | stat_insertion | 0 | 0 |  |  | 71 | 0 |
| scripted_ops_v1 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 1 |  |  |  |  |  |  |  | throughput_sla | 0 | 0 |  |  | 71 | 0 |

---

## Run info

| agent_baseline_id | episodes_per_second | n_episodes | partner_id | run_duration_wall_s | task |
| :--- | :--- | ---: | :--- | :--- | :--- |
| scripted_ops_v1 | 2.415 | 1 |  | 0.414 | throughput_sla |
| scripted_ops_v1 | 2.537 | 1 |  | 0.394 | stat_insertion |
| scripted_ops_v1 | 2.299 | 1 |  | 0.435 | qc_cascade |
| adversary_v1 | 2.76 | 1 |  | 0.362 | adversarial_disruption |
| scripted_ops_v1 | 2.215 | 1 |  | 0.452 | multi_site_stat |
| insider_v1 | 3.264 | 1 |  | 0.306 | insider_key_misuse |
| scripted_ops_v1 | 1.154 | 1 |  | 0.866 | coord_scale |
| scripted_ops_v1 | 1.167 | 1 |  | 0.857 | coord_risk |


---

*Summary generated from results.v0.2.*
