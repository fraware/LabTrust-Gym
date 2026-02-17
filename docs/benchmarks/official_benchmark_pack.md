# Official Benchmark Pack (v0.1 and v0.2)

The **Official Benchmark Pack** is a minimal, stable benchmark pack that external researchers can run and compare against. It uses a fixed set of tasks (A–H), scales (S/M/L), official baselines per task, official coordination methods, and security suite (smoke/full) definitions. Results semantics v0.2 remains canonical. The CLI is backward-compatible.

- **v0.1** (`benchmark_pack.v0.1.yaml`): Default for deterministic and scripted runs.
- **v0.2** (`benchmark_pack.v0.2.yaml`): Used automatically when `--pipeline-mode llm_live`. Adds the live coordination evaluation protocol (required metadata, cost accounting, reproducibility expectations) and writes `TRANSPARENCY_LOG/llm_live.json` and `live_evaluation_metadata.json`.

## Policy

Pack definition (default): `policy/official/benchmark_pack.v0.1.yaml`  
Pack definition (llm_live): `policy/official/benchmark_pack.v0.2.yaml` (loaded when `--pipeline-mode llm_live`)

- **tasks**: core (throughput_sla through insider_key_misuse), coordination (coord_scale, coord_risk), experimental (optional device_outage_surge, reagent_stockout)
- **scale_configs**: S (small), M (medium), L (large) with num_agents_total, horizon_steps, etc.
- **baselines**: method ID per task (e.g. scripted_ops_v1, adversary_v1, kernel_scheduler_or_v0)
- **coordination_methods**: list of method_ids (centralized_planner, hierarchical_hub_rr, llm_constrained)
- **security_suite**: smoke (enabled by default), full (optional)
- **required_reports**: security, safety_case, transparency_log

v0.2 adds **live_coordination_evaluation_protocol** with required_metadata_fields (model_id, temperature, tool_registry_fingerprint, allow_network), cost_accounting, and reproducibility_expectations (same seed/model/policy give comparable but not bit-identical results; attestation via hashes only).

## Exact command

```bash
labtrust run-official-pack --out <dir> --seed-base N
```

- **`--out`** (required): Output directory. Single folder ready to upload as "official pack result".
- **`--seed-base`** (default: 100): Base seed for deterministic runs.
- **`--smoke`**: Use smoke settings (fewer episodes, security smoke-only). Default when `LABTRUST_OFFICIAL_PACK_SMOKE=1` or `LABTRUST_PAPER_SMOKE=1`.
- **`--no-smoke`**: Disable smoke; run full pack (more episodes).
- **`--full`**: Run full security suite instead of smoke-only.
- **`--pipeline-mode`**: `deterministic` (default) or `llm_live`. With `llm_live`, the pack loads v0.2 policy, runs baselines with a live LLM backend, writes `TRANSPARENCY_LOG/llm_live.json` (prompt hashes, tool registry fingerprint, model identifiers, latency/cost stats; no sensitive prompt text) and `live_evaluation_metadata.json` (model_id, temperature, tool_registry_fingerprint, allow_network).
- **`--llm-backend`**: When `--pipeline-mode llm_live`, which backend to use: `openai_live`, `anthropic_live`, or `ollama_live`. Default is `openai_live` if not set. Requires the corresponding extra (e.g. `.[llm_anthropic]`) and env vars (e.g. `ANTHROPIC_API_KEY`).
- **`--allow-network`**: Allow network access (required for llm_live when using a remote API).
- **`--include-coordination-pack`**: Run the coordination security pack into `coordination_pack/` and build the lab report there (pack_summary.csv, pack_gate.md, SECURITY/coordination_risk_matrix.*, LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.*). Uses the pack policy `coordination_pack.matrix_preset` (default `hospital_lab`) when set; otherwise you can enable it in `policy/official/benchmark_pack.v0.1.yaml` with `coordination_pack: { enabled: true, matrix_preset: hospital_lab }`. See [Lab coordination report](../coordination/lab_coordination_report.md).

Example (smoke, fast):

```bash
LABTRUST_OFFICIAL_PACK_SMOKE=1 labtrust run-official-pack --out ./official_pack_result --seed-base 100
```

Example (full pack):

```bash
labtrust run-official-pack --out ./official_pack_result --seed-base 42 --no-smoke --full
```

Example (with coordination pack and lab report):

```bash
labtrust run-official-pack --out ./official_pack_result --seed-base 100 --include-coordination-pack
```

This produces `coordination_pack/` under the output dir with pack_summary.csv, pack_gate.md, SECURITY/coordination_risk_matrix.*, LAB_COORDINATION_REPORT.md, and COORDINATION_DECISION.*. See [Lab coordination report](../coordination/lab_coordination_report.md) for the canonical flow.

Example (llm_live, external reproducibility):

```bash
labtrust run-official-pack --out ./official_pack_result --seed-base 100 --pipeline-mode llm_live --allow-network
```

Report `model_id` and `temperature` (from `live_evaluation_metadata.json` or env) for reproducibility. The validator and risk-register exporter accept pack output that includes `TRANSPARENCY_LOG/llm_live.json` and `live_evaluation_metadata.json`; these are linked in the risk register when present.

## Cross-provider pack (run once per backend)

To run the same official pack with multiple LLM backends and get comparable outputs plus a merged summary:

```bash
labtrust run-cross-provider-pack --out <dir> --providers openai_live,anthropic_live,ollama_live [--seed-base N] [--smoke | --no-smoke]
```

- **`--out`** (required): Base output directory. Each provider gets a subdir: `<out>/openai_live/`, `<out>/anthropic_live/`, `<out>/ollama_live/` with the same tree as a single `run-official-pack` (baselines/, SECURITY/, SAFETY_CASE/, TRANSPARENCY_LOG/, llm_live.json, live_evaluation_metadata.json).
- **`--providers`**: Comma-separated list of backend IDs (`openai_live`, `anthropic_live`, `ollama_live`). Each must be installed and configured (API keys or local URL).
- **`--seed-base`**: Base seed for deterministic runs (default 100).
- **`--smoke`** / **`--no-smoke`**: Use smoke settings (fewer episodes) or full pack; default follows `LABTRUST_OFFICIAL_PACK_SMOKE` / `LABTRUST_PAPER_SMOKE`.

The command also writes **`<out>/summary_cross_provider.json`** and **`summary_cross_provider.md`** with model_id and mean_latency_ms per provider run for quick comparison.

## Expected output tree

After a successful run, `<out>` contains:

```
<out>/
  baselines/
    results/
      throughput_sla_scripted_ops.json
      stat_insertion_scripted_ops.json
      qc_cascade_scripted_ops.json
      adversarial_disruption_adversary.json
      multi_site_stat_scripted_ops.json
      insider_key_misuse_insider.json
      coord_scale_kernel_scheduler_or.json
      coord_risk_kernel_scheduler_or.json
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
    llm_live.json          (only when --pipeline-mode llm_live)
  coordination_pack/       (only when --include-coordination-pack or coordination_pack.enabled)
    pack_summary.csv
    pack_gate.md
    SECURITY/coordination_risk_matrix.csv, .md
    LAB_COORDINATION_REPORT.md
    COORDINATION_DECISION.v0.1.json, .md
    summary/
  pack_manifest.json
  live_evaluation_metadata.json   (only when --pipeline-mode llm_live)
  PACK_SUMMARY.md
```

**Validation:** Each results JSON under `baselines/results/` conforms to `policy/schemas/results.v0.2.schema.json`. You can run `labtrust summarize-results --in <out>/baselines/results/ --out <dir>` and use the summarize module's `validate_results_v02()` (or the CLI validate path) to verify. The pack layout and filenames above are stable for tooling and scripts.

- **baselines/results/**  
  One `results.v0.2`-semantics JSON per task (task name + baseline suffix). Produced by the same logic as `generate-official-baselines` but driven by the pack policy.

- **SECURITY/**  
  Security attack suite outputs (smoke or full) and securitization packet. Same layout as `labtrust run-security-suite --out <dir>`.

- **SAFETY_CASE/**  
  Safety case (claim → control → test → artifact → command). Same as `labtrust safety-case --out <dir>`.

- **coordination_pack/** (when `--include-coordination-pack` or pack policy `coordination_pack.enabled`)  
  Coordination security pack output plus lab report: pack_summary.csv, pack_gate.md, SECURITY/coordination_risk_matrix.*, LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.*, summary/. See [Lab coordination report](../coordination/lab_coordination_report.md).

- **TRANSPARENCY_LOG/**  
  Global transparency log over episode digests (when receipts or _repr exist). Otherwise a README.txt explains how to produce it (e.g. export-receipts then transparency-log).

- **pack_manifest.json**  
  Machine-readable manifest: version, pack_policy path, seed_base, timestamp, git_sha, smoke, pipeline_mode, allow_network, tasks, baselines, scale_configs, coordination_methods, required_reports, results_semantics.

- **TRANSPARENCY_LOG/llm_live.json** (llm_live only)  
  Transparency log for llm_live: prompt_hashes, tool_registry_fingerprint, model_version_identifiers, latency_and_cost_statistics, per_task. Reviewable without exposing sensitive prompt text.

- **live_evaluation_metadata.json** (llm_live only)  
  Required protocol fields: model_id, temperature, tool_registry_fingerprint, allow_network.

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
