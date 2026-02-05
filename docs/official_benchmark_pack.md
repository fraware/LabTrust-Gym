# Official Benchmark Pack v0.1

The **Official Benchmark Pack** is a minimal, stable benchmark pack that external researchers can run and compare against. It uses a fixed set of tasks (A–H), scales (S/M/L), official baselines per task, official coordination methods, and security suite (smoke/full) definitions. Results semantics v0.2 remains canonical. The CLI is backward-compatible.

## Policy

Pack definition: `policy/official/benchmark_pack.v0.1.yaml`

- **tasks**: core (TaskA–TaskF), coordination (TaskG, TaskH), experimental (optional TaskI/J)
- **scale_configs**: S (small), M (medium), L (large) with num_agents_total, horizon_steps, etc.
- **baselines**: method ID per task (e.g. scripted_ops_v1, adversary_v1, kernel_scheduler_or_v0)
- **coordination_methods**: list of method_ids (centralized_planner, hierarchical_hub_rr, llm_constrained)
- **security_suite**: smoke (enabled by default), full (optional)
- **required_reports**: security, safety_case, transparency_log

## Exact command

```bash
labtrust run-official-pack --out <dir> --seed-base N
```

- **`--out`** (required): Output directory. Single folder ready to upload as "official pack result".
- **`--seed-base`** (default: 100): Base seed for deterministic runs.
- **`--smoke`**: Use smoke settings (fewer episodes, security smoke-only). Default when `LABTRUST_OFFICIAL_PACK_SMOKE=1` or `LABTRUST_PAPER_SMOKE=1`.
- **`--no-smoke`**: Disable smoke; run full pack (more episodes).
- **`--full`**: Run full security suite instead of smoke-only.

Example (smoke, fast):

```bash
LABTRUST_OFFICIAL_PACK_SMOKE=1 labtrust run-official-pack --out ./official_pack_result --seed-base 100
```

Example (full pack):

```bash
labtrust run-official-pack --out ./official_pack_result --seed-base 42 --no-smoke --full
```

## Expected output tree

After a successful run, `<out>` contains:

```
<out>/
  baselines/
    results/
      TaskA_scripted_ops.json
      TaskB_scripted_ops.json
      TaskC_scripted_ops.json
      TaskD_adversary.json
      TaskE_scripted_ops.json
      TaskF_insider.json
      TaskG_kernel_scheduler_or.json
      TaskH_kernel_scheduler_or.json
  SECURITY/
    attack_results.json
    coverage.json
    coverage.md
    reason_codes.md
    deps_inventory_runtime.json
    (securitization packet)
  SAFETY_CASE/
    safety_case.json
    safety_case.md
  TRANSPARENCY_LOG/
    log.json
    root.txt
    proofs/
    (or README.txt if no receipts yet)
  pack_manifest.json
  PACK_SUMMARY.md
```

- **baselines/results/**  
  One `results.v0.2`-semantics JSON per task (task name + baseline suffix). Produced by the same logic as `generate-official-baselines` but driven by the pack policy.

- **SECURITY/**  
  Security attack suite outputs (smoke or full) and securitization packet. Same layout as `labtrust run-security-suite --out <dir>`.

- **SAFETY_CASE/**  
  Safety case (claim → control → test → artifact → command). Same as `labtrust safety-case --out <dir>`.

- **TRANSPARENCY_LOG/**  
  Global transparency log over episode digests (when receipts or _repr exist). Otherwise a README.txt explains how to produce it (e.g. export-receipts then transparency-log).

- **pack_manifest.json**  
  Machine-readable manifest: version, pack_policy path, seed_base, timestamp, git_sha, smoke, tasks, baselines, scale_configs, coordination_methods, required_reports, results_semantics.

- **PACK_SUMMARY.md**  
  Human-readable pack summary table and output tree (as above).

## Verification

To check that a pack result is valid and that receipts (if present) verify:

```bash
labtrust verify-bundle --bundle <out>/receipts/<task>
```

Smoke tests (`tests/test_official_pack_smoke.py`) run the pack with `LABTRUST_OFFICIAL_PACK_SMOKE=1` (or `LABTRUST_PAPER_SMOKE=1`), assert required folders exist, and run verify-bundle where applicable.

## Relation to package-release

The `paper_v0.1` profile of `labtrust package-release` references the official pack policy and includes a pack summary table (e.g. in RELEASE_NOTES or PACK_SUMMARY) so that the paper artifact documents the same benchmark pack definition.

## Backward compatibility

Existing CLI commands (`run-benchmark`, `generate-official-baselines`, `run-security-suite`, `safety-case`, `transparency-log`, `package-release`) are unchanged. `run-official-pack` composes them into one folder for the community to replicate.
