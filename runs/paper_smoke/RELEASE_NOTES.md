# Paper-ready release (profile paper_v0.1)

## What ran

- **Official baselines**: Tasks A–F, 1 episodes each, seed_base=100.
- **TaskF study**: strict_signatures ablation (false/true), 2 episodes per condition, seed_base=100.
- **Summarize**: combined official + study results → TABLES/summary.csv, TABLES/summary.md, TABLES/paper_table.md.
- **Representative runs**: 1 episode per task with episode log → export receipts → verify bundle (receipts/<task>/).

## Versions and seeds

- Git SHA: f168410be388f50462178ea9e0defffd0483857b
- Seed base: 100
- Timestamp (deterministic when seed-base set): 1970-01-01T00:01:40Z

## Layout

- `_baselines/`: official baseline results (results/, summary.csv, summary.md, metadata.json).
- `_study/`: TaskF strict_signatures study (manifest.json, results/, logs/, figures/).
- `FIGURES/`: canonical plots from TaskF study.
- `TABLES/`: summary.csv, summary.md, paper_table.md.
- `receipts/<task>/`: EvidenceBundle.v0.1 and verify_report.txt per task.
- `_repr/`: one representative run per task (episodes.jsonl, results.json).
- `SECURITY/`: attack_results.json (security attack suite), coverage.md, coverage.json, reason_codes.md, deps_inventory.json, deps_inventory_runtime.json (securitization packet).
- `TRANSPARENCY_LOG/`: log.json (append-only episode digests), root.txt (Merkle root), proofs/<episode_id>.json (inclusion proofs).
- `SAFETY_CASE/`: safety_case.json, safety_case.md (claim -> control -> test -> artifact -> command).
- `COORDINATION_CARD.md`: coordination benchmark card (TaskG/TaskH; scenario generation, scale configs, methods, injections, metrics, determinism, limitations, policy fingerprint).
- `_coordination_policy/`: frozen copy of policy/coordination/ files used for the card; manifest.json contains coordination_policy_fingerprint and per-file sha256.

## Official Benchmark Pack (v0.1)

The **Official Benchmark Pack** is defined in `policy/official/benchmark_pack.v0.1.yaml`. Community replication: `labtrust run-official-pack --out <dir> --seed-base N`. See [Official Benchmark Pack](docs/official_benchmark_pack.md).

| Item | Value |
|------|-------|
| Pack policy | policy/official/benchmark_pack.v0.1.yaml |
| Tasks | TaskA–TaskF (core), TaskG–TaskH (coordination) |
| Scale configs | S (small), M (medium), L (large) |
| Baselines | scripted_ops_v1, adversary_v1, insider_v1, kernel_scheduler_or_v0 |
| Coordination methods | centralized_planner, hierarchical_hub_rr, llm_constrained |
| Required reports | security, safety_case, transparency_log |
| Results semantics | v0.2 |
