# CI gates and regression

CI runs on every push/PR to `main` and keeps the default pipeline **fast**. All CI jobs use **pipeline_mode=deterministic** (no LLM, no network); `--allow-network` and `LABTRUST_ALLOW_NETWORK` are not set, so the environment stays offline. Optional benchmark smoke runs only on **schedule** (nightly) or when **manually triggered** with "Run benchmark smoke" enabled.

## Gates (always run on push/PR)

| Job             | Description                    | Command / notes           |
|-----------------|--------------------------------|----------------------------|
| **lint-format** | Ruff format + check            | `ruff format --check .`    |
| **typecheck**   | Mypy on `src/`                 | `mypy src/`                |
| **test**        | Pytest (fast suite, excludes slow) | Matrix: **ubuntu-latest**, **windows-latest** × Python **3.11**, **3.12**; `pytest -q -m "not slow"`; slow tests (golden suite, package-release) are marked `@pytest.mark.slow` and use pytest-timeout (see pyproject.toml) |
| **golden**      | Determinism-report then full golden suite (real engine) | Determinism-report (throughput_sla, 3 episodes, seed 42); then `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q` (timeout 35 min) |
| **risk-coverage-every-pr** | Risk coverage (strict) on every PR | `labtrust export-risk-register --out ./risk_register_out --runs tests/fixtures/ui_fixtures` then `labtrust validate-coverage --bundle ./risk_register_out/RISK_REGISTER_BUNDLE.v0.1.json --strict` |
| **coverage**    | Code coverage (every PR) | `pytest -q -m "not slow" --cov=src/labtrust_gym --cov-report=xml --cov-report=term`; uploads coverage.xml artifact |
| **policy-validate** | Policy YAML/JSON vs schemas | `labtrust validate-policy` |
| **release-fixture-verify** | Release chain regression anchor (verify-release --strict-fingerprints on committed fixture) | `pytest tests/test_release_fixture_verify_release.py -v`. Fixture at `tests/fixtures/release_fixture_minimal`; build with `scripts/build_release_fixture.sh` (or `.ps1`). Any change that breaks release invariants fails here even if golden passes. See [Release checklist](release_checklist.md). |
| **risk-register-gate** | Risk register contract (schema, snapshot, crosswalk, coverage) | `labtrust export-risk-register --out ./risk_register_out --runs tests/fixtures/ui_fixtures` then `pytest tests/test_risk_register_contract_gate.py -v` |
| **quick-eval**  | 1 episode throughput_sla, adversarial_disruption, multi_site_stat   | `pip install -e ".[env,plots]"` then `labtrust quick-eval --seed 42 --out-dir ./labtrust_runs` |
| **baseline-regression** | Compare to canonical frozen v0.2 (exact metrics) | `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`; non-skipping when `benchmarks/baselines_official/v0.2/results/*.json` exist |
| **docs**        | Build MkDocs site and deploy to GitHub Pages (site + viewer + viewer-data/latest) | `pip install -e ".[docs]"`, `mkdocs build --strict`, `build_viewer_data_from_release.sh`, copy viewer/ and viewer-data/ into site/, upload Pages artifact |
| **wheel-smoke** | Build wheel, install in venv, **audit-selfcheck** (doctor), validate-policy, quick-eval | `.github/workflows/wheel-smoke.yml`; fails if audit-selfcheck exits non-zero (missing env deps caught early) |
| **paper-claims-regression** | Paper snapshot regression (schedule / workflow_dispatch only) | `LABTRUST_PAPER_SMOKE=1 pytest tests/test_paper_claims_regression.py -v`; compares built paper artifact to committed snapshot at tests/fixtures/paper_claims_snapshot/v0.1; timeout 15 min |

The **test** job runs on a **matrix** of **ubuntu-latest** and **windows-latest** with Python 3.11 and 3.12 so regressions on either OS or version are caught. The default **test** job excludes slow tests via `-m "not slow"` so CI stays fast. Long-running tests (e.g. package_release, full golden suite, benchmark multi_site_stat/insider_key_misuse, determinism-report) are marked with `@pytest.mark.slow` and run in the **golden** job or on demand. pytest-timeout is configured in `pyproject.toml` (default 120s per test); see `addopts` and `markers` in pyproject.toml. The **golden suite** runs in a separate **golden** job on every push/PR and must stay green. It validates scenario correctness against the engine contract. Slow tests (golden, package-release, heavy CLI) are excluded from the default **test** job via `-m "not slow"` so CI stays bounded.

### Test skip conditions and required fixtures

Some tests skip when fixtures or environment are missing. To avoid unnecessary skips and interpret results:

| Condition | Tests affected | What to do |
|-----------|----------------|------------|
| **LABTRUST_RUN_GOLDEN** unset | `test_golden_suite.py` | Set `LABTRUST_RUN_GOLDEN=1` to run the full golden suite (e.g. in the **golden** CI job). |
| **ui_fixtures evidence bundle** missing or invalid | `test_cli_verify_bundle`, `test_risk_register_contract_gate` (e.g. `test_ui_fixtures_evidence_bundle_verifies`) | Ensure `tests/fixtures/ui_fixtures/evidence_bundle/EvidenceBundle.v0.1/` exists and passes `labtrust verify-bundle --bundle tests/fixtures/ui_fixtures/evidence_bundle/EvidenceBundle.v0.1`. Regenerate per risk_register_contract_gate snapshot workflow if needed. |
| **Benchmark baselines (v0.2)** missing | `test_official_baselines_regression.py` | Run `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force` and commit results; or accept skip when v0.2/results/ is empty. |
| **Coordination / MARL / LLM** optional deps | Coordination interface tests, `train_ppo` / `eval_ppo` CLI smoke | Install `.[env]` for coordination; MARL/PPO tests skip without trained model or `LABTRUST_CLI_FULL`; live LLM tests skip without `OPENAI_API_KEY`. |
| **Repo root / policy path** not found | Schema and policy tests | Run from repo root so `policy/` and `policy/schemas/` are found. |

CI jobs that depend on a fixture (e.g. **risk-register-gate** on ui_fixtures evidence bundle) fail with a clear error when the fixture is missing; use the "What to do" column to fix. See [Evaluation checklist](../benchmarks/evaluation_checklist.md) and this document for full CI and local commands.

### Verification battery (local)

To run the same set of checks as CI in one sequence (lint, typecheck, no-placeholders, validate-policy, verify-bundle, risk-register gate, pytest fast, golden suite, determinism-report, quick-eval, baseline-regression if baselines exist, docs build):

```bash
pip install -e ".[dev,env,docs]"
make verification-battery
```

Or run the script directly: `bash scripts/run_verification_battery.sh` (from repo root). The script sets `LABTRUST_RUN_GOLDEN=1` for the golden suite so it does not skip. **Required:** ui_fixtures evidence bundle at `tests/fixtures/ui_fixtures/evidence_bundle/EvidenceBundle.v0.1` (see [Test skip conditions and required fixtures](#test-skip-conditions-and-required-fixtures)). **Optional:** set `LABTRUST_BATTERY_E2E=1` to also run the e2e-artifacts-chain (package-release minimal → export-risk-register → build-release-manifest → verify-release --strict-fingerprints) at the end. The **release fixture** test (`test_release_fixture_verify_release.py`) runs as part of the default test suite when the fixture dir is present; it enforces verify-release --strict-fingerprints on the committed fixture. See [Evaluation checklist](../benchmarks/evaluation_checklist.md) for the full list of steps.

## Coverage report and ratchet

Job **coverage** runs on **every push/PR**. It runs `pytest -q -m "not slow" --cov=src/labtrust_gym --cov-report=xml --cov-report=term` and uploads **coverage.xml** as a workflow artifact. Configuration: `[tool.coverage.run]` and `[tool.coverage.report]` in `pyproject.toml` at repo root.

**Coverage ratchet:** A **fail_under** value is set in pyproject.toml so that coverage regressions are **PR-blocking**. The coverage job fails when line coverage falls below that percentage. Start conservative to avoid churn; ratchet up over time.

**Ratchet policy:**

| Item | Value |
|------|--------|
| **Current floor** | 60% (see `fail_under` in pyproject.toml) |
| **Cadence** | Raise by +5 percentage points every 4 weeks until target is reached. |
| **Target** | 80% (adjust in ci.md and pyproject.toml when raising). |
| **Who** | Maintainer raises `fail_under` and updates this table on the agreed cadence. |

To run locally: `pip install -e ".[dev]"` then `pytest -q -m "not slow" --cov=src/labtrust_gym --cov-report=term`. The same `fail_under` applies locally when using pytest-cov.

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

## Deterministic vs non-deterministic runs

**Deterministic runs** (reproducible with the same seed): default `pytest -q`, `labtrust quick-eval`, `labtrust package-release` and `labtrust run-benchmark` when no live LLM or network is used, and CI jobs that do not set `LABTRUST_RUN_LLM_LIVE`, `OPENAI_API_KEY`, or `--llm-backend openai_live` / `ollama_live` / `anthropic_live`. No outbound API calls; results depend only on seed and code.

**Non-deterministic runs**: any run that uses a live LLM (e.g. `LABTRUST_RUN_LLM_LIVE=1`, `--llm-backend openai_live`, or `OPENAI_API_KEY` set and live calls made) or other external services. Outputs can vary between runs. In scripts and CI, non-deterministic runs must be clearly labeled (e.g. job name "llm_live smoke", env var in description) and should not be the default path for regression.

## Pre-online hardening

Before enabling online or non-deterministic runs in production:

- **Deterministic baseline remains default:** CI and default CLI do not use live LLM or network; regression uses deterministic backends.
- **Real LLM behind a flag:** Use `--llm-backend openai_live` / `ollama_live` / `anthropic_live` and `--allow-network` (or `LABTRUST_ALLOW_NETWORK=1`) explicitly; do not default to live backends.
- **API keys from environment only:** No hardcoded keys; use `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. from the process environment. If you use a `.env` file, load it explicitly before running (see [Installation](../getting-started/installation.md#loading-a-env-file-optional)).
- **Non-deterministic runs clearly labeled:** CI jobs that run with live LLM or network must have distinct job names and document required secrets; see [Optional: LLM live E2E in CI](#optional-llm-live-e2e-in-ci).

See [Evaluation checklist](../benchmarks/evaluation_checklist.md) for verification and audit steps.

## Risk coverage (strict) — schedule / manual and path-filtered PR

Job **risk-coverage-strict** in the main CI workflow runs **only on schedule or workflow_dispatch** (not on every push/PR). It builds the risk register bundle from `tests/fixtures/ui_fixtures` and runs **`labtrust validate-coverage --strict`**. The job fails if any required_bench cell in the method–risk matrix has no evidence in the bundle. To pass: add evidence (e.g. run the coordination security pack or study, then `labtrust export-risk-register --runs <pack_or_study_out> --out <dir>` and use that bundle; or add coordination matrix / run artifacts to the ui_fixtures so the fixture bundle covers all required cells). See [Risk register](../risk-and-security/risk_register.md).

**Path-filtered PR:** Workflow **`.github/workflows/risk-coverage-pr.yml`** runs **validate-coverage --strict** on pull requests (and push to main) when files under `policy/coordination/`, `policy/risks/`, `tests/fixtures/ui_fixtures/`, or `src/labtrust_gym/export/risk_register_bundle.py` (or related export/risk_register code) change. This reduces the risk that required_bench coverage regresses without detection on relevant PRs. To enforce required_bench coverage on every push, add a job that runs `labtrust validate-coverage --strict` after export-risk-register from ui_fixtures (heavier; current design uses path-filtered PR and schedule).

## Optional: LLM live E2E in CI

The **llm_live_optional_smoke** workflow (`.github/workflows/llm_live_optional_smoke.yml`) runs when `OPENAI_API_KEY` is set (workflow_dispatch or schedule). It runs healthcheck and official-pack smoke with `--pipeline-mode llm_live`, then **asserts E2E**: non-empty `model_id` in live_evaluation_metadata.json and non-empty `model_version_identifiers.llm_model_id` plus at least one of mean_latency_ms / estimated_cost_usd / total_tokens in TRANSPARENCY_LOG/llm_live.json. This job is **not** required for merge (opt-in when secret is set). Required secrets: `OPENAI_API_KEY`. See [Optional: LLM live E2E in CI](#optional-llm-live-e2e-in-ci) above.

## Determinism and golden suite

**Determinism report** runs the benchmark twice with identical args (throughput_sla, 3 episodes, seed 42) and asserts v0.2 metrics and episode log hash identical. **Full golden suite** runs all scenarios with the real engine (`LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`).

**Determinism budget (enforced gate):** The determinism report is a **gate**, not just an artifact. The **golden** job fails if the report does not pass. Thresholds are defined in `src/labtrust_gym/benchmarks/determinism_report.py`:

| Requirement | Threshold | Effect |
|-------------|-----------|--------|
| **Hashchain reproducibility** | Exact match | Episode log SHA-256 must be identical between the two runs. No tolerance. |
| **Throughput jitter** | `max_throughput_delta` | Per-episode throughput differences must not exceed this (default 0: exact match). |
| **Latency (p95) jitter** | `max_p95_latency_delta` | Per-episode p95 turnaround differences (seconds) must not exceed this (default 0: exact match). |
| **v0.2 metrics** | Canonical identical | Normalized v0.2 metrics comparison; if not identical, numeric deltas are checked against the jitter thresholds above. |

If any check fails, `determinism_report.json` has `"passed": false` and the golden job step that asserts `passed` fails, blocking the PR.

**When it runs:**

- **Golden job** runs on **every push/PR** (job **golden** in the main CI workflow). It runs **determinism-report** first, then the full golden suite. Both must pass.
- **determinism-golden** (separate job in ci.yml) runs only on schedule or workflow_dispatch.
- **PRs that touch core paths:** Workflow **`.github/workflows/determinism-golden.yml`** also runs determinism-report when relevant paths change. Recommend adding **golden** (and optionally determinism-golden when it runs) as required status checks in branch protection.

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
   coord_scale and coord_risk at S scale (small_smoke), 1 episode each, for methods `kernel_whca`, `ripple_effect`, `consensus_paxos_lite`, `swarm_stigmergy_priority`; coord_risk with INJ-COMMS-POISON-001. Writes `labtrust_runs/coordination_nightly/sota_sanity/<id>_taskg.json` and `<id>_taskh_poison.json`.

4. **Layer 3 at-scale (one profile)**  
   coord_scale with `kernel_whca`, scale `corridor_heavy`, 1 episode (seed 300). Writes `labtrust_runs/coordination_nightly/at_scale/kernel_whca_taskg_corridor_heavy.json`. See [Benchmarking plan](../benchmarks/benchmarking_plan.md) Layer 2/3: full Layer 2 matrix is via coordination study spec; Layer 3 profile is covered here in nightly.

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

See [Benchmarking plan](../benchmarks/benchmarking_plan.md#security-stress-matrix-coordination-security-pack) and [Security attack suite](../risk-and-security/security_attack_suite.md#coordination-security-pack-internal-regression).

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
  - `make verify` — full verification battery (lint, typecheck, validate-policy, risk-register gate, pytest, golden, determinism-report, quick-eval, baseline-regression if baselines exist, docs build). See [Evaluation checklist](../benchmarks/evaluation_checklist.md).  
  - `make paper OUT=<dir>` — paper-ready artifact (package-release paper_v0.1 then verify-release).  
  - `make golden` — golden suite  
  - `make bench-smoke` — 1 episode per task (needs `.[env]`)  
  - `make bench-smoke-pytest` — pytest benchmark smoke tests (2 episodes throughput_sla + determinism)  
  - `make e2e-artifacts-chain` — full e2e reproducible chain (package-release → determinism-report → verify-release → export-risk-register; no network). See [E2E artifacts chain](#e2e-artifacts-chain) below.

- **Release fixture (regression anchor):**  
  `pytest tests/test_release_fixture_verify_release.py -v` runs verify-release --strict-fingerprints on `tests/fixtures/release_fixture_minimal`. Build the fixture with `scripts/build_release_fixture.sh` (or `.ps1`); commit the fixture so the gate stays green. See [Release checklist](release_checklist.md).

- **Required-bench coverage pack (deterministic evidence):**  
  `scripts/run_required_bench_matrix.sh --out runs/required_bench_pack` (or `.ps1` with `-OutDir`) runs security suite smoke + coordination security pack, then export-risk-register and validate-coverage --strict. Coverage becomes a build product. See [Risk register](../risk-and-security/risk_register.md#required-bench-coverage-pack-deterministic).

- **Full benchmark smoke tests (pytest):**  
  `pytest tests/test_benchmark_smoke.py -v`

- **Baseline regression guard (compare to frozen v0.2):**  
  `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`  
  Requires: official results in `benchmarks/baselines_official/v0.2/results/*.json` (generate with the command in **Baseline regression guard** above).

## E2E artifacts chain

(Nightly / manual.) Workflow **`.github/workflows/e2e-artifacts-chain.yml`** runs the full reproducible artifact chain with no network:

- **When:** On push to `main`, pull requests targeting `main`, **workflow_dispatch**, or nightly schedule.
- **Steps:** `scripts/ci_e2e_artifacts_chain.sh` — package-release (minimal profile), determinism-report (throughput_sla, 3 episodes, seed 42), verify-release (all EvidenceBundles under the release), export-risk-register from the release dir. The job fails if any step or crosswalk validation fails.
- **Run locally:** `make e2e-artifacts-chain` or `bash scripts/ci_e2e_artifacts_chain.sh` (deterministic; same seed-base as script default).

## LLM live optional smoke (nightly / manual)

Workflow **`.github/workflows/llm_live_optional_smoke.yml`** runs live-LLM healthcheck and official-pack smoke when API keys are available:

- **When:** **workflow_dispatch** or nightly. **Skips** when `OPENAI_API_KEY` is not set (no failure).
- **Steps:** `labtrust llm-healthcheck --backend openai_responses`; then official pack smoke with llm_live (`--pipeline-mode llm_live`, `--allow-network`). **E2E assertion:** non-empty model_id and latency/cost in TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json. Uploads those artifacts as workflow artifacts.
- **Secrets:** Set `OPENAI_API_KEY` in repo secrets to enable the job; without it, the workflow exits successfully without running live calls.

## Viewer data from release (path-filtered)

Workflow **`.github/workflows/viewer-data-from-release.yml`** builds **viewer-data/latest/** from the release artifact chain so the risk register viewer can show "latest release" bundle:

- **When:** Push/PR when `viewer/`, `viewer-data/`, `policy/risks/`, or risk-register/package_release code change; or **workflow_dispatch**.
- **Steps:** `scripts/build_viewer_data_from_release.sh` runs package-release (minimal), export-risk-register, copies `RISK_REGISTER_BUNDLE.v0.1.json` and writes `latest.json` (git_sha, version, generated_at, bundle_file) into `viewer-data/latest/`; then schema and crosswalk validation on the bundle. Uploads `viewer-data/latest/` as artifact.
- **Viewer:** Open the viewer and use "Load latest release" to fetch `viewer-data/latest/latest.json` then the referenced bundle (when served over HTTP, e.g. GitHub Pages with artifact or deployed content). See [Risk register viewer](../risk-and-security/risk_register_viewer.md).

## Package-release (nightly only)

A separate workflow **`.github/workflows/package-release-nightly.yml`** runs **package-release** (reproduce + export receipts + export FHIR + plots + MANIFEST + BENCHMARK_CARD):

- **When:** Scheduled (e.g. 03:00 UTC) or **workflow_dispatch** (manual "Run workflow").
- **Steps:** Install `.[dev,env,plots]`, run `labtrust package-release --profile minimal --out release_artifact --seed-base 100` with `LABTRUST_REPRO_SMOKE=1`, upload **release_artifact/** as a workflow artifact (retention 7 days).
- **Profiles:** `minimal` | `full` (reproduce throughput_sla & qc_cascade + receipts/FHIR) or **paper_v0.1** (baselines + insider_key_misuse study + FIGURES/TABLES + receipts; see [Paper provenance](../benchmarks/paper/README.md)). Paper profile can be run locally with `LABTRUST_PAPER_SMOKE=1` for a fast smoke.
- **Not run on push/PR:** Default CI does **not** run package-release so the pipeline stays fast.

## Release workflow (tag v*)

**`.github/workflows/release.yml`** runs on push of tags `v*` (e.g. `v0.1.0`):

- Copies `policy/` into `src/labtrust_gym/policy` so the wheel ships policy.
- Builds sdist and wheel with `python -m build`.
- Uploads `dist/` as artifact. A **publish** job (structure only) can use twine; add `TWINE_PASSWORD` (and optionally `TWINE_USERNAME`) in repo secrets to enable PyPI upload.

## Summary

- **Default CI:** lint, typecheck, test (includes golden), policy-validate, **release-fixture-verify** (verify-release --strict-fingerprints on committed fixture at tests/fixtures/release_fixture_minimal; top-level truth gate), **risk-register-gate** (generate bundle from tests/fixtures/ui_fixtures, schema + contract gate tests: snapshot, crosswalk, coverage), **baseline-regression** (compares against canonical v0.2; non-skipping when v0.2 exists), **quick-eval** (throughput_sla, adversarial_disruption, multi_site_stat), docs (MkDocs build). **viewer-data-from-release** runs when viewer/viewer-data/policy/risks or risk-register/package_release code changes. No benchmark smoke, no package-release on every PR.
- **Baseline regression:** Job runs `pytest tests/test_official_baselines_regression.py` with `LABTRUST_CHECK_BASELINES=1`. Test uses **benchmarks/baselines_official/v0.2/** only; runs (does not skip) when v0.2/results/*.json exist. To update baselines, run `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force` (matches regression params) and commit the results.
- **Nightly / manual:** same plus bench-smoke (1 episode per task) when `LABTRUST_BENCH_SMOKE=1`; **coordination-smoke** (validate-policy, coordination tests, coord_scale + coord_risk one episode) when `LABTRUST_COORDINATION_SMOKE=1`; **package-release** artifact when workflow `package-release-nightly` runs; **e2e-artifacts-chain** (package-release → verify-release → export-risk-register) via `e2e-artifacts-chain.yml`; **llm_live optional smoke** (healthcheck + pack smoke, artifact upload) via `llm_live_optional_smoke.yml` when `OPENAI_API_KEY` is set.
- Golden suite must remain green on every run. Documentation site is built on every PR; deploy to GitHub Pages via `.github/workflows/docs.yml` on push to `main`.
