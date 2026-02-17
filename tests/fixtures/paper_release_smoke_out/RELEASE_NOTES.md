# Paper-ready release (profile paper_v0.1)

## What ran

- **Official baselines**: Tasks A–F, 1 episodes each, seed_base=42.
- **insider_key_misuse study**: strict_signatures ablation (false/true), 2 episodes per condition, seed_base=42.
- **Summarize**: combined official + study results → TABLES/summary.csv, TABLES/summary.md, TABLES/paper_table.md.
- **Representative runs**: 1 episode per task with episode log → export receipts → verify bundle (receipts/<task>/).

## Versions and seeds

- Git SHA: d8a110a1dd9f07ad85b9bd527ae15be8b6ef1de1
- Seed base: 42
- Timestamp (deterministic when seed-base set): 1970-01-01T00:00:42Z

## Layout

- `_baselines/`: official baseline results (results/, summary.csv, summary.md, metadata.json).
- `_study/`: insider_key_misuse strict_signatures study (manifest.json, results/, logs/, figures/).
- `FIGURES/`: canonical plots from insider_key_misuse study.
- `TABLES/`: summary.csv, summary.md, paper_table.md.
- `receipts/<task>/`: EvidenceBundle.v0.1 and verify_report.txt per task.
- `_repr/`: one representative run per task (episodes.jsonl, results.json).
- `SECURITY/`: attack_results.json (security attack suite), coverage.md, coverage.json, reason_codes.md, deps_inventory.json, deps_inventory_runtime.json (securitization packet).
- `TRANSPARENCY_LOG/`: log.json (append-only episode digests), root.txt (Merkle root), proofs/<episode_id>.json (inclusion proofs).
- `SAFETY_CASE/`: safety_case.json, safety_case.md (claim -> control -> test -> artifact -> command).
- `COORDINATION_MATRIX/`: COORDINATION_MATRIX.v0.1.json (matrix artifact; from pack when --include-coordination-pack), README.md (how produced; llm_live or pack mode).
- `COORDINATION_CARD.md`: coordination benchmark card (coord_scale/coord_risk; scenario generation, scale configs, methods, injections, metrics, determinism, limitations, policy fingerprint).
- `COORDINATION_LLM_CARD.md`: LLM coordination card (LLM methods, backends, policy fingerprint, injection coverage, known limitations).
- `_coordination_policy/`: frozen copy of policy/coordination/ files used for the card; manifest.json contains coordination_policy_fingerprint and per-file sha256.


## Official Benchmark Pack (v0.1)

The **Official Benchmark Pack** is defined in `policy/official/benchmark_pack.v0.1.yaml`. Community replication: `labtrust run-official-pack --out <dir> --seed-base N`. See [Official Benchmark Pack](docs/official_benchmark_pack.md).

| Item | Value |
|------|-------|
| Pack policy | policy/official/benchmark_pack.v0.1.yaml |
| Tasks | throughput_sla–insider_key_misuse (core), coord_scale–coord_risk (coordination) |
| Scale configs | S (small), M (medium), L (large) |
| Baselines | scripted_ops_v1, adversary_v1, insider_v1, kernel_scheduler_or_v0 |
| Coordination methods | centralized_planner, hierarchical_hub_rr, llm_constrained |
| Required reports | security, safety_case, transparency_log |
| Results semantics | v0.2 |
