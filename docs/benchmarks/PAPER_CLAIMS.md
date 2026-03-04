# Paper claims and figure/table provenance

Concrete claims supported by this repository and its artifacts. Update with experiment pointers and figure numbers when publishing.

## Supported claims

1. **Trust skeleton**  
   The environment enforces a trust skeleton: RBAC, signed actions, hash-chained audit log, invariant registry and enforcement, reason codes, tokens, zones, specimens, QC, critical results, catalogue, stability, queueing, transport.  
   *Artifacts:* `policy/` (schemas and YAML), `src/labtrust_gym/engine/`, `src/labtrust_gym/policy/`.  
   *Tests:* Golden suite (35 scenarios) with `LABTRUST_RUN_GOLDEN=1`; `tests/test_golden_suite.py`, policy validation `tests/test_policy_validation.py`.

2. **Benchmarks and baselines**  
   Tasks (throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk) with scripted, adversary, LLM, and MARL (PPO) baselines; official pack v0.1/v0.2; security suite and safety case.  
   *Artifacts:* `benchmarks/`, `policy/official/benchmark_pack.v0.1.yaml`, `policy/official/benchmark_pack.v0.2.yaml`, `policy/safety_case/claims.v0.1.yaml`.  
   *Tests:* `tests/test_benchmark_smoke.py`, `tests/test_official_pack_smoke.py`, `tests/test_safety_case_generation.py`.

3. **Reproducibility**  
   Deterministic runs via `seed_base` and `seed_offset`; package-release profiles (minimal, full, paper_v0.1) produce MANIFEST, receipts, FHIR, FIGURES, TABLES; verify-bundle validates evidence bundle.  
   *Artifacts:* `labtrust package-release --profile paper_v0.1`, `labtrust reproduce --profile minimal|full`.  
   *Docs:* [Paper provenance](paper/README.md), [Reproduce](reproduce.md).

4. **Coordination and red team**  
   Multiple coordination methods (centralized, hierarchical, market, gossip, swarm, kernel+EDF/WHCA/auction, LLM planners); coordination security pack with fixed scale x method x injection matrix; red-team injections v0.2 with success/detection/containment definitions.  
   *Artifacts:* `policy/coordination/injections.v0.2.yaml`, `policy/coordination/coordination_security_pack.v0.1.yaml`, `src/labtrust_gym/baselines/coordination/` (and policy/coordination/).  
   *Tests:* `tests/test_coordination_security_pack.py`, `tests/test_coord_red_team_definitions.py`.

5. **Prompt-injection defense**  
   Pre-LLM block, optional truncate/redact sanitization, output consistency; pattern-based detection and golden scenarios.  
   *Artifacts:* `policy/security/prompt_injection_defense.v0.1.yaml`, `policy/golden/prompt_injection_scenarios.v0.1.yaml`.  
   *Tests:* `tests/test_prompt_injection_defense.py`, `tests/test_llm_prompt_injection_golden.py`.

## Figure/table provenance

See [Paper provenance](paper/README.md) for commands that generate figures and tables (e.g. `labtrust package-release --profile paper_v0.1`, `labtrust make-plots`, `labtrust run-study`).

## Paper claims regression gate

Paper-facing outputs (summary, safety case, coverage, risk register) are gated by a committed snapshot so PRs cannot change them without an explicit snapshot update. **Committed snapshot:** `tests/fixtures/paper_claims_snapshot/v0.1/` (snapshot_manifest.json and optional summary.csv). **Extract script:** `scripts/extract_paper_claims_snapshot.py <release_dir> [--out <dir>]` writes a deterministic snapshot from a paper_v0.1 release. **Comparison:** `labtrust_gym.studies.paper_claims_compare.compare_paper_snapshot(release_dir, snapshot_dir)` (optional_keys for non-deterministic artifacts like SECURITY/coverage.json). **Test:** `tests/test_paper_claims_regression.py` builds a minimal paper artifact (LABTRUST_PAPER_SMOKE=1), extracts, compares to the committed snapshot; see `tests/fixtures/paper_claims_snapshot/README.md` for how to update the snapshot. **CI:** Job `paper-claims-regression` runs on schedule and workflow_dispatch (see [CI](../operations/ci.md)).
