# Official Benchmark Pack v0.2 – Pack summary

| Item | Value |
|------|-------|
| Pack policy | policy/official/benchmark_pack.v0.2.yaml |
| Seed base | 100 |
| Timestamp | 1970-01-01T00:01:40Z |
| Git SHA | 7563446fff1e |
| Smoke | False |
| Tasks | throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk |
| Scale configs | S, M, L |
| Coordination methods | centralized_planner, hierarchical_hub_rr, llm_constrained |
| Required reports | security, safety_case, transparency_log |
| Pipeline mode | llm_live |

## Output tree

```
baselines/results/   (results per task)
SECURITY/            (attack_results.json, coverage, deps)
SAFETY_CASE/         (safety_case.json, safety_case.md)
TRANSPARENCY_LOG/    (log.json, root.txt, proofs/ or README; llm_live.json if llm_live)
pack_manifest.json
coordination_pack/     (pack_summary.csv, pack_gate.md, SECURITY/, LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.*)
live_evaluation_metadata.json   (live evaluation metadata: model_id, wall_clock_s_*, llm_latency_ms_* when present)
PACK_SUMMARY.md
```
