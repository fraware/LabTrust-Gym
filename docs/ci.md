# CI gates and regression

CI runs on every push/PR to `main` and keeps the default pipeline **fast**. All CI jobs use **pipeline_mode=deterministic** (no LLM, no network); `--allow-network` and `LABTRUST_ALLOW_NETWORK` are not set, so the environment stays offline. Optional benchmark smoke runs only on **schedule** (nightly) or when **manually triggered** with "Run benchmark smoke" enabled.

## Gates (always run on push/PR)

| Job             | Description                    | Command / notes           |
|-----------------|--------------------------------|----------------------------|
| **lint-format** | Ruff format + check            | `ruff format --check .`    |
| **typecheck**   | Mypy on `src/`                 | `mypy src/`                |
| **test**        | Pytest (fast suite)            | `pytest -q`                |
| **policy-validate** | Policy YAML/JSON vs schemas | `labtrust validate-policy` |
| **risk-register-gate** | Risk register contract (schema, snapshot, crosswalk, coverage) | `labtrust export-risk-register --out ./risk_register_out --runs ui_fixtures` then `pytest tests/test_risk_register_contract_gate.py -v` |
| **quick-eval**  | 1 episode throughput_sla, adversarial_disruption, multi_site_stat   | `pip install -e ".[env,plots]"` then `labtrust quick-eval --seed 42 --out-dir ./labtrust_runs` |
| **baseline-regression** | Compare to canonical frozen v0.2 (exact metrics) | `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`; non-skipping when `benchmarks/baselines_official/v0.2/results/*.json` exist |
| **docs**        | Build MkDocs site              | `pip install -e ".[docs]"` then `mkdocs build --strict` |

The **golden suite** is included in the default `pytest -q` run and must stay green. It validates scenario correctness against the engine contract.

## Optional: benchmark smoke

When **LABTRUST_BENCH_SMOKE=1**, an extra job **bench-smoke** runs:

- Installs `.[dev,env]` (adds PettingZoo/Gymnasium).
- Runs **1 episode per task** (throughput_sla, stat_insertion, qc_cascade) via `labtrust bench-smoke --seed 42`.

**When it runs:**

- **Nightly**: scheduled workflow (e.g. 02:00 UTC) sets `LABTRUST_BENCH_SMOKE=1`.
- **Manual**: use "Run workflow" in the Actions tab and check **Run benchmark smoke (1 episode per task)**.

**When it does not run:** Normal push/PR do **not** set `LABTRUST_BENCH_SMOKE`, so the bench-smoke job is skipped and CI stays fast.

## Optional: coordination smoke

When **LABTRUST_COORDINATION_SMOKE=1**, an extra job **coordination-smoke** runs:

- Installs `.[dev,env]`.
- Runs `labtrust validate-policy`.
- Runs `pytest -q tests/test_coordination_*` (all coordination-related tests).
- Runs `labtrust run-benchmark --task coord_scale --episodes 1 --seed 42 --coord-method centralized_planner --out ./taskg_smoke.json`.
- Runs `labtrust run-benchmark --task coord_risk --episodes 1 --seed 42 --coord-method market_auction --injection INJ-COLLUSION-001 --out ./taskh_smoke.json`.

**When it runs:** Nightly schedule or manual "Run workflow" with **Run coordination smoke** enabled. No secrets required. Normal push/PR do not set `LABTRUST_COORDINATION_SMOKE`, so the job is skipped.

## Pack smoke on PR (path-filtered)

Workflow **`.github/workflows/pack-smoke-pr.yml`** runs a **lightweight** coordination security pack on pull requests when files under `src/labtrust_gym/studies/`, `src/labtrust_gym/benchmarks/`, or `policy/coordination/` (or related tests) change. It runs `labtrust run-coordination-security-pack --out ./pack_smoke --methods-from fixed --injections-from critical --seed 42` and asserts `pack_smoke/pack_summary.csv` exists. If the pack fails or the summary is missing, the workflow fails and the build is red. PRs that do not touch those paths skip this workflow.

## Optional: external reviewer checks

When **LABTRUST_EXTERNAL_REVIEWER_CHECKS=1**, an extra job **external-reviewer-checks** runs:

- Installs `.[dev,env]`.
- Runs `scripts/run_external_reviewer_checks.sh ./external_reviewer_out tests/fixtures/coordination_study_llm_smoke_spec.yaml`: coordination study (deterministic), validates `summary/summary_coord.csv` and required columns, **coverage gate** (every required_bench (method_id, risk_id) from the method-risk matrix has at least one row in the summary), optionally verify-bundle, ensures or generates `COORDINATION_LLM_CARD.md`.
- **Coverage gate**: By default missing (method_id, risk_id) cells are reported and the script continues (exit 0). Set **LABTRUST_STRICT_COVERAGE=1** to exit 1 when any required_bench cell is missing.

**When it runs:** Nightly schedule or manual "Run workflow" with **Run external reviewer checks** enabled. No network, no secrets. To run the same locally with the full spec: `bash scripts/run_external_reviewer_checks.sh <out_dir> policy/coordination/coordination_study_spec.v0.1.yaml`.

**Windows:** The script may fail with CRLF line endings (e.g. `set -eu` parsed incorrectly). Use WSL or ensure shell scripts use LF (`.gitattributes` sets `*.sh text eol=lf` on checkout).

## Determinism and golden suite

**Determinism report** runs the benchmark twice with identical args (throughput_sla, 3 episodes, seed 42) and asserts v0.2 metrics and episode log hash identical. **Full golden suite** runs all scenarios with the real engine (`LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`).

**When it runs:**

- **CI (main workflow):** Job **determinism-golden** runs only on **schedule** or **workflow_dispatch** (not on every push/PR), so default CI stays fast.
- **PRs that touch core paths:** Workflow **`.github/workflows/determinism-golden.yml`** runs on pull requests when files under `src/labtrust_gym/engine/`, `src/labtrust_gym/runner/`, `src/labtrust_gym/benchmarks/runner.py`, or `src/labtrust_gym/studies/coordination_*` (or golden/determinism tests) change. You can add **determinism-golden** as a required status check for those PRs in branch protection.

**To run locally:**

```bash
labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report
LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q
```

## Coordination nightly (separate workflow)

Workflow **`.github/workflows/coordination-nightly.yml`** runs a heavier coordination regression set **only on schedule or manual dispatch**. It does **not** run on push/PR, so default CI stays fast.

**When it runs:** **schedule** (cron 02:30 UTC) or **workflow_dispatch** (Actions tab, "Run workflow" for "Coordination nightly").

**Steps (single job):**

1. **Coordination security pack**  
   `labtrust run-coordination-security-pack --out ./labtrust_runs/coordination_nightly/pack --seed 42`  
   Fixed scale x method x injection matrix, 1 ep/cell; writes pack_results/, pack_summary.csv, pack_gate.md.

2. **Coordination study (smoke spec)**  
   `labtrust run-coordination-study --spec tests/fixtures/coordination_study_external_reviewer_spec.yaml --out ./labtrust_runs/coordination_nightly/study_smoke --llm-backend deterministic`  
   Small matrix (e.g. 3 methods x 4 injections, 1 ep/cell); produces summary_coord.csv and pareto.md.

3. **SOTA sanity (minimal subset)**  
   coord_scale and coord_risk at S scale (small_smoke), 1 episode each, for methods `kernel_whca` and `ripple_effect`; coord_risk with INJ-COMMS-POISON-001. Writes `labtrust_runs/coordination_nightly/sota_sanity/<id>_taskg.json` and `<id>_taskh_poison.json`.

No network, no secrets. To run the same locally:

```bash
labtrust run-coordination-security-pack --out ./labtrust_runs/coordination_nightly/pack --seed 42
labtrust run-coordination-study --spec tests/fixtures/coordination_study_external_reviewer_spec.yaml --out ./labtrust_runs/coordination_nightly/study_smoke --llm-backend deterministic
# Then run Layer 1 sanity for kernel_whca and ripple_effect with 1 episode (or use scripts/run_benchmarking_layer1_sanity.sh with LABTRUST_SANITY_METHODS="kernel_whca ripple_effect" and reduce episodes if desired).
```

## Coordination security full matrix (separate workflow)

Workflow **`.github/workflows/coordination-security-full.yml`** runs the coordination security pack with **all methods** (from policy, except marl_ppo) and **all injections** (from injections.v0.2 that are implemented in INJECTION_REGISTRY). It does **not** run on push/PR.

**When it runs:** **schedule** (cron 03:00 UTC Sundays) or **workflow_dispatch** (Actions tab, "Run workflow" for "Coordination security full matrix").

**Steps:**

1. **Full coordination security pack**  
   `labtrust run-coordination-security-pack --out ./labtrust_runs/coordination_security_full/pack --methods-from full --injections-from policy --seed 42`  
   Matrix size: (all registry methods) x (all policy injections) x 2 scales; 1 ep/cell. Writes pack_results/, pack_summary.csv, pack_gate.md.

2. **Upload artifacts**  
   Uploads pack_summary.csv and pack_gate.md as workflow artifacts for review.

To run the full matrix locally:

```bash
labtrust run-coordination-security-pack --out ./labtrust_runs/coord_security_full --methods-from full --injections-from policy --seed 42
labtrust summarize-coordination --in ./labtrust_runs/coord_security_full --out ./labtrust_runs/coord_security_full/summary
```

See [Benchmarking plan](benchmarking_plan.md#security-stress-matrix-coordination-security-pack) and [Security attack suite](security_attack_suite.md#coordination-security-pack-internal-regression).

## Baseline regression guard

When **LABTRUST_CHECK_BASELINES=1**, the **baseline-regression** job runs (and is included in CI):

- Installs `.[dev,env]`.
- Runs **`pytest tests/test_official_baselines_regression.py -v`**.
- The test compares current run (episodes=3, seed=123, timing=explicit) for Tasks A–F to **canonical frozen v0.2**: **`benchmarks/baselines_official/v0.2/results/*.json`**. Compared metrics (strict subset for cross-OS stability): `throughput`, `holds_count`, `tokens_minted`, `tokens_consumed`, `steps`, `blocked_by_reason_code`, `violations_by_invariant_id`. Float metrics are omitted.
- **v0.2 is canonical**; the test prefers v0.2 and runs (non-skipping) when v0.2/results/ exists with at least one *.json. If v0.2 is missing or empty, the test **skips** with a message to generate baselines.

**How to update baselines (PR-8 baseline update command):** To intentionally update the frozen directory (e.g. after a benchmark or policy change), regenerate and freeze official results, then commit the updated files:

```bash
labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 200 --seed 123 --force
```

To produce a minimal set for CI (episodes=3, seed=123) only:

```bash
labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force
```

Then run `labtrust summarize-results --in benchmarks/baselines_official/v0.2/results --out benchmarks/baselines_official/v0.2 --basename summary` if you want updated summary tables. Commit `benchmarks/baselines_official/v0.2/results/*.json`, `summary.csv`, `summary.md`, and `metadata.json`.

## Running the same locally

- **Golden suite only:**  
  `pytest tests/test_golden_suite.py -q`

- **Benchmark smoke (1 episode per task):**  
  `labtrust bench-smoke --seed 42`  
  Requires: `pip install -e ".[env]"`

- **Make:**  
  - `make golden` — golden suite  
  - `make bench-smoke` — 1 episode per task (needs `.[env]`)  
  - `make bench-smoke-pytest` — pytest benchmark smoke tests (2 episodes throughput_sla + determinism)  
  - `make e2e-artifacts-chain` — full e2e reproducible chain (package-release minimal → verify-release → export-risk-register; no network). See [E2E artifacts chain](#e2e-artifacts-chain) below.

- **Full benchmark smoke tests (pytest):**  
  `pytest tests/test_benchmark_smoke.py -v`

- **Baseline regression guard (compare to frozen v0.2):**  
  `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`  
  Requires: official results in `benchmarks/baselines_official/v0.2/results/*.json` (generate with the command in **Baseline regression guard** above).

## E2E artifacts chain

(Nightly / manual.) Workflow **`.github/workflows/e2e-artifacts-chain.yml`** runs the full reproducible artifact chain with no network:

- **When:** On push/PR (optional job), **workflow_dispatch**, or nightly schedule.
- **Steps:** `scripts/ci_e2e_artifacts_chain.sh` — package-release (minimal profile), verify-release (all EvidenceBundles under the release), export-risk-register from the release dir. The job fails if any step or crosswalk validation fails.
- **Run locally:** `make e2e-artifacts-chain` or `bash scripts/ci_e2e_artifacts_chain.sh` (deterministic; same seed-base as script default).

## LLM live optional smoke (nightly / manual)

Workflow **`.github/workflows/llm_live_optional_smoke.yml`** runs live-LLM healthcheck and official-pack smoke when API keys are available:

- **When:** **workflow_dispatch** or nightly. **Skips** when `OPENAI_API_KEY` is not set (no failure).
- **Steps:** `labtrust llm-healthcheck --backend openai_live`; then official pack smoke with llm_live (`LABTRUST_OFFICIAL_PACK_SMOKE=1`, `--pipeline-mode llm_live`, `--allow-network`). Uploads llm_live pack artifacts (e.g. TRANSPARENCY_LOG/llm_live.json, live_evaluation_metadata.json) as workflow artifacts.
- **Secrets:** Set `OPENAI_API_KEY` in repo secrets to enable the job; without it, the workflow exits successfully without running live calls.

## Package-release (nightly only)

A separate workflow **`.github/workflows/package-release-nightly.yml`** runs **package-release** (reproduce + export receipts + export FHIR + plots + MANIFEST + BENCHMARK_CARD):

- **When:** Scheduled (e.g. 03:00 UTC) or **workflow_dispatch** (manual "Run workflow").
- **Steps:** Install `.[dev,env,plots]`, run `labtrust package-release --profile minimal --out release_artifact --seed-base 100` with `LABTRUST_REPRO_SMOKE=1`, upload **release_artifact/** as a workflow artifact (retention 7 days).
- **Profiles:** `minimal` | `full` (reproduce throughput_sla & qc_cascade + receipts/FHIR) or **paper_v0.1** (baselines + insider_key_misuse study + FIGURES/TABLES + receipts; see [Paper-ready release](paper_ready.md)). Paper profile can be run locally with `LABTRUST_PAPER_SMOKE=1` for a fast smoke.
- **Not run on push/PR:** Default CI does **not** run package-release so the pipeline stays fast.

## Release workflow (tag v*)

**`.github/workflows/release.yml`** runs on push of tags `v*` (e.g. `v0.1.0`):

- Copies `policy/` into `src/labtrust_gym/policy` so the wheel ships policy.
- Builds sdist and wheel with `python -m build`.
- Uploads `dist/` as artifact. A **publish** job (structure only) can use twine; add `TWINE_PASSWORD` (and optionally `TWINE_USERNAME`) in repo secrets to enable PyPI upload.

## Summary

- **Default CI:** lint, typecheck, test (includes golden), policy-validate, **risk-register-gate** (generate bundle from ui_fixtures, schema + contract gate tests: snapshot, crosswalk, coverage), **baseline-regression** (compares against canonical v0.2; non-skipping when v0.2 exists), **quick-eval** (throughput_sla, adversarial_disruption, multi_site_stat), docs (MkDocs build). No benchmark smoke, no package-release.
- **Baseline regression:** Job runs `pytest tests/test_official_baselines_regression.py` with `LABTRUST_CHECK_BASELINES=1`. Test uses **benchmarks/baselines_official/v0.2/** only; runs (does not skip) when v0.2/results/*.json exist. To update baselines, run `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force` (matches regression params) and commit the results.
- **Nightly / manual:** same plus bench-smoke (1 episode per task) when `LABTRUST_BENCH_SMOKE=1`; **coordination-smoke** (validate-policy, coordination tests, coord_scale + coord_risk one episode) when `LABTRUST_COORDINATION_SMOKE=1`; **package-release** artifact when workflow `package-release-nightly` runs; **e2e-artifacts-chain** (package-release → verify-release → export-risk-register) via `e2e-artifacts-chain.yml`; **llm_live optional smoke** (healthcheck + pack smoke, artifact upload) via `llm_live_optional_smoke.yml` when `OPENAI_API_KEY` is set.
- Golden suite must remain green on every run. Documentation site is built on every PR; deploy to GitHub Pages via `.github/workflows/docs.yml` on push to `main`.
