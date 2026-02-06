# Official Benchmark Pack v0.1 – Pack summary

| Item | Value |
|------|-------|
| Pack policy | policy/official/benchmark_pack.v0.1.yaml |
| Seed base | 42 |
| Timestamp | 1970-01-01T00:00:42Z |
| Git SHA | f168410be388 |
| Smoke | False |
| Tasks | TaskA, TaskB, TaskC, TaskD, TaskE, TaskF, TaskG, TaskH |
| Scale configs | S, M, L |
| Coordination methods | centralized_planner, hierarchical_hub_rr, llm_constrained |
| Required reports | security, safety_case, transparency_log |

## Output tree

```
baselines/results/   (results per task)
SECURITY/            (attack_results.json, coverage, deps)
SAFETY_CASE/         (safety_case.json, safety_case.md)
TRANSPARENCY_LOG/    (log.json, root.txt, proofs/ or README)
pack_manifest.json
PACK_SUMMARY.md
```
