# Reproducing results and figures

A single CLI path reproduces a minimal set of study results and figures: a small ablation sweep (trust on/off, dual approval on/off) for **throughput_sla** and **qc_cascade**, then plots and data tables.

## Requirements

- `pip install -e ".[env,plots]"` or `pip install labtrust-gym[env,plots]` (PettingZoo + matplotlib for study runner and plots)
- Policy path: run from repo root (policy under `policy/`), or from an installed wheel (policy shipped in package), or set `LABTRUST_POLICY_DIR` to the policy directory

## Reproducibility and seeding

LabTrust-Gym is deterministic when seeds and config are fixed.

- **Golden runner**: `reset(initial_state, deterministic=True, rng_seed=<from scenario>)`. The engine uses a single RNG wrapper (`engine/rng.py`); no ambient `random` outside it.
- **Benchmarks**: `run_episode(task, episode_seed, ...)` passes `episode_seed` into env `reset(seed=episode_seed, options={"initial_state": ...})`. Same task + same seed ⇒ same episode trajectory and metrics.
- **Studies**: Condition seeds are `seed_base + condition_index`. Same spec + same code + same seeds ⇒ identical manifest and per-condition result hashes.
- **Plots**: Data tables (CSVs) are deterministic; same study run ⇒ identical CSV output.

**Timing modes:** **explicit** (default) — event `t_s` is explicit; no simulated device service times. **simulated** — device service times from equipment registry; RNG samples from policy. Set `initial_state.timing_mode: "simulated"` (or via study spec) to enable.

**Policy and versions:** Policy files are versioned under `policy/`. Validate with `labtrust validate-policy`. Study manifest records policy paths and (when available) file hashes for reproducibility.

**Official pack and llm_live:** For Official Benchmark Pack runs with `--pipeline-mode llm_live`, same seed, model, and policy yield comparable but not bit-identical results (LLM non-determinism). The v0.2 pack defines reproducibility expectations and requires metadata (model_id, temperature, tool_registry_fingerprint, allow_network). Attestation uses hashes and policy fingerprints only (no sensitive prompt text in artifacts): `TRANSPARENCY_LOG/llm_live.json` records prompt hashes, tool registry fingerprint, model identifiers, and latency/cost statistics.

**End-to-end artifact validation:** To confirm that export, verify, risk register, and UI export plumbing all hold, run the minimal release then validate workflow (package-release minimal → verify-release or verify-bundle → export-risk-register → ui-export). Acceptance: verify-bundle succeeds (hashchain, manifest, schema, invariant trace); risk register builds with no crosswalk failures; UI zip is produced and loadable. See [Artifacts are reproducible end-to-end](#artifacts-are-reproducible-end-to-end).

## Commands

### Minimal run (few episodes, fast)

```bash
labtrust reproduce --profile minimal
```

- **Sweep**: `trust_skeleton` [on, off] × `dual_approval` [on, off] → 4 conditions per task.
- **Tasks**: throughput_sla, qc_cascade (2 study runs).
- **Episodes per condition**: 2 (or 1 when `LABTRUST_REPRO_SMOKE=1`).
- **Output**: `runs/repro_minimal_<YYYYMMDD_HHMMSS>/` with:
  - `spec_throughput_sla.yaml`, `spec_qc_cascade.yaml`
  - `taska/` and `taskc/`: `manifest.json`, `conditions.jsonl`, `results/`, `logs/`, `figures/`, `figures/data_tables/`

### Full run (more episodes)

```bash
labtrust reproduce --profile full
```

- Same sweep and tasks; **4 episodes** per condition (or 1 when `LABTRUST_REPRO_SMOKE=1`).
- Output: `runs/repro_full_<YYYYMMDD_HHMMSS>/` with the same layout.

### Custom output directory

```bash
labtrust reproduce --profile minimal --out runs/my_repro
```

Writes under `runs/my_repro/` (relative to repo root if not absolute).

## Expected runtime

- **Minimal** (2 episodes/condition, 4 conditions × 2 tasks = 8 study runs): about **1–3 minutes** on a typical laptop, depending on hardware.
- **Minimal with smoke** (`LABTRUST_REPRO_SMOKE=1`, 1 episode/condition): about **30–90 seconds**.
- **Full** (4 episodes/condition): about **2–6 minutes**.

Exact times depend on CPU and whether timing is `explicit` (faster) or `simulated`.

## Smoke test (CI / validation)

To only check that the command runs in minimal mode with a tiny episode count:

```bash
LABTRUST_REPRO_SMOKE=1 labtrust reproduce --profile minimal --out runs/repro_smoke
```

With `LABTRUST_REPRO_SMOKE=1`, every condition runs **1 episode** regardless of profile. The test `tests/test_reproduce_smoke.py` runs this under pytest when the env var is set.

## Output layout

```
runs/repro_minimal_<timestamp>/
  spec_throughput_sla.yaml
  spec_qc_cascade.yaml
  taska/
    manifest.json
    conditions.jsonl
    results/cond_0/results.json ... cond_3/results.json
    logs/cond_0/episodes.jsonl ...
    figures/
      throughput_vs_violations.png, .svg
      trust_cost_vs_p95_tat.png, .svg
      violations_by_invariant_id.png, .svg
      blocked_by_reason_code_top10.png, .svg
      critical_compliance_by_condition.png, .svg
      throughput_box_by_condition.png, .svg
      metrics_overview.png, .svg
      RUN_REPORT.md
    figures/data_tables/
      throughput_vs_violations.csv
      trust_cost_vs_p95_tat.csv
      violations_by_invariant_id.csv
      blocked_by_reason_code_top10.csv
      critical_compliance_by_condition.csv
  taskc/
    (same structure)
```

## Exporting receipts (evidence bundle)

After a minimal (or full) run, you can export **Receipt.v0.1** and **EvidenceBundle.v0.1** from any episode log. Example for minimal profile:

```bash
# 1) Produce a run
labtrust reproduce --profile minimal --out runs/my_repro

# 2) Export receipts from one condition's episode log (e.g. first condition, first task)
labtrust export-receipts --run runs/my_repro/taska/logs/cond_0/episodes.jsonl --out runs/my_repro/taska/cond_0_export
```

This creates `runs/my_repro/taska/cond_0_export/EvidenceBundle.v0.1/` with receipt JSON files per specimen/result, episode_log_subset.jsonl, invariant_eval_trace.jsonl, enforcement_actions.jsonl, hashchain_proof.json, and manifest.json. Exported receipts validate against `policy/schemas/receipt.v0.1.schema.json`; the manifest validates against `policy/schemas/evidence_bundle_manifest.v0.1.schema.json`.

### Export FHIR R4

From the same evidence bundle you can export a minimal FHIR R4 Bundle (Specimen, Observation, DiagnosticReport):

```bash
labtrust export-fhir --receipts runs/my_repro/taska/cond_0_export/EvidenceBundle.v0.1 --out runs/my_repro/taska/cond_0_fhir
```

This writes `runs/my_repro/taska/cond_0_fhir/fhir_bundle.json`. See [FHIR R4 export](fhir_export.md) for mapping rules and limitations.

## Package release (single-command artifact)

To produce an **external-facing release artifact** (results, plots, receipts, FHIR, benchmark card, manifest with hashes) in one step:

```bash
labtrust package-release --profile minimal --out /tmp/labtrust_release
```

Profiles: **minimal** | **full** (reproduce throughput_sla & qc_cascade sweep + plots) or **paper_v0.1** (benchmark-first: official baselines + insider_key_misuse strict_signatures study + summarize + receipts + FIGURES/TABLES). For paper-ready artifact and exact commands, see [Paper-ready release](paper_ready.md).

- **minimal/full** run **reproduce** (throughput_sla & qc_cascade sweep + plots), then **export-receipts** and **export-fhir** per condition, and write:
  - `MANIFEST.v0.1.json` — list of files with SHA-256 (deterministic for fixed `--seed-base`)
  - `BENCHMARK_CARD.md` — scope, invariants, tasks A–F, baselines, limitations (see [Benchmark card](benchmark_card.md))
  - `metadata.json` — git SHA, partner_id, policy_fingerprint, seed_base, timestamp
  - `results.json` — study manifests summary
  - `results/` — results.json per task (v0.2 schema; `agent_baseline_id`, `git_sha`, etc.)
  - `summary.csv` and `summary.md` — leaderboard table (mean/std by task + baseline + partner_id); see `labtrust summarize-results`
  - `plots/` — figures (PNG/SVG) per task
  - `tables/` — CSV data tables per task
  - `receipts/` — EvidenceBundle.v0.1 per task/condition
  - `fhir/` — FHIR R4 bundles per task/condition

Use **`--seed-base N`** for deterministic artifacts (same seed ⇒ identical MANIFEST file hashes). Optional **`--keep-repro`** keeps the intermediate `_repro` directory.

## Artifacts are reproducible end-to-end

This workflow validates export, verify, risk register, UI export, and (optionally) paper artifact plumbing. Run it after producing a minimal release to confirm the full pipeline holds.

**One-command option (no network, deterministic):** Run the full chain locally with:

```bash
make e2e-artifacts-chain
```

or directly:

```bash
bash scripts/ci_e2e_artifacts_chain.sh
```

This runs package-release (minimal), verify-bundle, and export-risk-register; the script fails on any step or crosswalk failure.

### Minimal release artifact (fast)

```bash
labtrust package-release --profile minimal --seed-base 100 --out /tmp/labtrust_release_min
```

### Verify at least one evidence bundle

Point `--bundle` at an **EvidenceBundle.v0.1** directory produced by the release (e.g. under `receipts/<task>_<cond>/`). Example:

```bash
labtrust verify-bundle --bundle /tmp/labtrust_release_min/receipts/taska_cond_0/EvidenceBundle.v0.1
```

If your release uses different condition IDs, use the path to any `EvidenceBundle.v0.1` under `receipts/`. This checks manifest integrity, schema validation, hashchain proof, and invariant trace.

### Risk register bundle generation

```bash
labtrust export-risk-register --out /tmp/risk_register_out --runs /tmp/labtrust_release_min
```

The bundle is written to `/tmp/risk_register_out/RISK_REGISTER_BUNDLE.v0.1.json`. It must build with no crosswalk failures.

### UI export smoke (optional but recommended)

```bash
labtrust ui-export --run /tmp/labtrust_release_min --out /tmp/ui_bundle.zip
```

The zip should be produced and loadable by the UI (index, events, receipts_index, reason_codes).

### Acceptance

- **verify-bundle** succeeds: hashchain proof, manifest, schema, and invariant trace all pass.
- **Risk register bundle** builds with no crosswalk failures.
- **UI export** zip is produced and loadable.

On Windows use a writable output path (e.g. `%TEMP%\labtrust_release_min`) instead of `/tmp/...` if needed.

## Summarize results (leaderboard table)

To aggregate one or more `results.json` (or directories containing them) into a comparable table:

```bash
labtrust summarize-results --in results/ your_run.json --out /tmp/summary --basename summary
```

Writes **summary.csv** and **summary.md** with mean/std for throughput, p50/p95 TAT, on_time_rate, violations, critical_communication_compliance_rate, detection_latency_s, containment_success, grouped by task + agent_baseline_id + partner_id. Compare to the official baseline table in `benchmarks/baselines_official/v0.1/` or regenerate v0.2 with `labtrust generate-official-baselines` (see [Benchmark card](benchmark_card.md)).

## See also

- [Studies and plots](studies.md) for the full study runner and plotting pipeline
- [Benchmarks](benchmarks.md) for task definitions and metrics
- [Benchmark card](benchmark_card.md) for results schema v0.2 and official baseline table
- [Paper-ready release](paper_ready.md) for the **paper_v0.1** profile (baselines + insider_key_misuse study + FIGURES/TABLES)
- [Enforcement](enforcement.md) for the evidence bundle section and export-receipts CLI
