# CI gates and regression

CI runs on every push/PR to `main` and keeps the default pipeline **fast**. Optional benchmark smoke runs only on **schedule** (nightly) or when **manually triggered** with "Run benchmark smoke" enabled.

## Gates (always run on push/PR)

| Job             | Description                    | Command / notes           |
|-----------------|--------------------------------|----------------------------|
| **lint-format** | Ruff format + check            | `ruff format --check .`    |
| **typecheck**   | Mypy on `src/`                 | `mypy src/`                |
| **test**        | Pytest (fast suite)            | `pytest -q`                |
| **policy-validate** | Policy YAML/JSON vs schemas | `labtrust validate-policy` |
| **quick-eval**  | 1 episode TaskA, TaskD, TaskE   | `pip install -e ".[env,plots]"` then `labtrust quick-eval --seed 42 --out-dir ./labtrust_runs` |
| **baseline-regression** | Compare to canonical frozen v0.2 (exact metrics) | `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`; non-skipping when `benchmarks/baselines_official/v0.2/results/*.json` exist |
| **docs**        | Build MkDocs site              | `pip install -e ".[docs]"` then `mkdocs build --strict` |

The **golden suite** is included in the default `pytest -q` run and must stay green. It validates scenario correctness against the engine contract.

## Optional: benchmark smoke

When **LABTRUST_BENCH_SMOKE=1**, an extra job **bench-smoke** runs:

- Installs `.[dev,env]` (adds PettingZoo/Gymnasium).
- Runs **1 episode per task** (TaskA, TaskB, TaskC) via `labtrust bench-smoke --seed 42`.

**When it runs:**

- **Nightly**: scheduled workflow (e.g. 02:00 UTC) sets `LABTRUST_BENCH_SMOKE=1`.
- **Manual**: use "Run workflow" in the Actions tab and check **Run benchmark smoke (1 episode per task)**.

**When it does not run:** Normal push/PR do **not** set `LABTRUST_BENCH_SMOKE`, so the bench-smoke job is skipped and CI stays fast.

## Optional: coordination smoke

When **LABTRUST_COORDINATION_SMOKE=1**, an extra job **coordination-smoke** runs:

- Installs `.[dev,env]`.
- Runs `labtrust validate-policy`.
- Runs `pytest -q tests/test_coordination_*` (all coordination-related tests).
- Runs `labtrust run-benchmark --task TaskG_COORD_SCALE --episodes 1 --seed 42 --coord-method centralized_planner --out ./taskg_smoke.json`.
- Runs `labtrust run-benchmark --task TaskH_COORD_RISK --episodes 1 --seed 42 --coord-method market_auction --injection INJ-COLLUSION-001 --out ./taskh_smoke.json`.

**When it runs:** Nightly schedule or manual "Run workflow" with **Run coordination smoke** enabled. No secrets required. Normal push/PR do not set `LABTRUST_COORDINATION_SMOKE`, so the job is skipped.

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
  - `make bench-smoke-pytest` — pytest benchmark smoke tests (2 episodes TaskA + determinism)

- **Full benchmark smoke tests (pytest):**  
  `pytest tests/test_benchmark_smoke.py -v`

- **Baseline regression guard (compare to frozen v0.2):**  
  `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`  
  Requires: official results in `benchmarks/baselines_official/v0.2/results/*.json` (generate with the command in **Baseline regression guard** above).

## Package-release (nightly only)

A separate workflow **`.github/workflows/package-release-nightly.yml`** runs **package-release** (reproduce + export receipts + export FHIR + plots + MANIFEST + BENCHMARK_CARD):

- **When:** Scheduled (e.g. 03:00 UTC) or **workflow_dispatch** (manual "Run workflow").
- **Steps:** Install `.[dev,env,plots]`, run `labtrust package-release --profile minimal --out release_artifact --seed-base 100` with `LABTRUST_REPRO_SMOKE=1`, upload **release_artifact/** as a workflow artifact (retention 7 days).
- **Profiles:** `minimal` | `full` (reproduce TaskA & TaskC + receipts/FHIR) or **paper_v0.1** (baselines + TaskF study + FIGURES/TABLES + receipts; see [Paper-ready release](paper_ready.md)). Paper profile can be run locally with `LABTRUST_PAPER_SMOKE=1` for a fast smoke.
- **Not run on push/PR:** Default CI does **not** run package-release so the pipeline stays fast.

## Release workflow (tag v*)

**`.github/workflows/release.yml`** runs on push of tags `v*` (e.g. `v0.1.0`):

- Copies `policy/` into `src/labtrust_gym/policy` so the wheel ships policy.
- Builds sdist and wheel with `python -m build`.
- Uploads `dist/` as artifact. A **publish** job (structure only) can use twine; add `TWINE_PASSWORD` (and optionally `TWINE_USERNAME`) in repo secrets to enable PyPI upload.

## Summary

- **Default CI:** lint, typecheck, test (includes golden), policy-validate, **baseline-regression** (compares against canonical v0.2; non-skipping when v0.2 exists), **quick-eval** (TaskA, TaskD, TaskE), docs (MkDocs build). No benchmark smoke, no package-release.
- **Baseline regression:** Job runs `pytest tests/test_official_baselines_regression.py` with `LABTRUST_CHECK_BASELINES=1`. Test uses **benchmarks/baselines_official/v0.2/** only; runs (does not skip) when v0.2/results/*.json exist. To update baselines, run `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force` (matches regression params) and commit the results.
- **Nightly / manual:** same plus bench-smoke (1 episode per task) when `LABTRUST_BENCH_SMOKE=1`; **coordination-smoke** (validate-policy, coordination tests, TaskG + TaskH one episode) when `LABTRUST_COORDINATION_SMOKE=1`; **package-release** artifact when workflow `package-release-nightly` runs.
- Golden suite must remain green on every run. Documentation site is built on every PR; deploy to GitHub Pages via `.github/workflows/docs.yml` on push to `main`.
