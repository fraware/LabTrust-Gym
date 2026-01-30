# CI gates and regression

CI runs on every push/PR to `main` and keeps the default pipeline **fast**. Optional benchmark smoke runs only on **schedule** (nightly) or when **manually triggered** with "Run benchmark smoke" enabled.

## Gates (always run on push/PR)

| Job             | Description                    | Command / notes           |
|-----------------|--------------------------------|----------------------------|
| **lint-format** | Ruff format + check            | `ruff format --check .`    |
| **typecheck**   | Mypy on `src/`                 | `mypy src/`                |
| **test**        | Pytest (fast suite)            | `pytest -q`                |
| **policy-validate** | Policy YAML/JSON vs schemas | `labtrust validate-policy` |

The **golden suite** is included in the default `pytest -q` run and must stay green. It validates scenario correctness against the engine contract.

## Optional: benchmark smoke

When **LABTRUST_BENCH_SMOKE=1**, an extra job **bench-smoke** runs:

- Installs `.[dev,env]` (adds PettingZoo/Gymnasium).
- Runs **1 episode per task** (TaskA, TaskB, TaskC) via `labtrust bench-smoke --seed 42`.

**When it runs:**

- **Nightly**: scheduled workflow (e.g. 02:00 UTC) sets `LABTRUST_BENCH_SMOKE=1`.
- **Manual**: use "Run workflow" in the Actions tab and check **Run benchmark smoke (1 episode per task)**.

**When it does not run:** Normal push/PR do **not** set `LABTRUST_BENCH_SMOKE`, so the bench-smoke job is skipped and CI stays fast.

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

## Summary

- **Default CI:** lint, typecheck, test (includes golden), policy-validate. No benchmark smoke.
- **Nightly / manual:** same plus bench-smoke (1 episode per task) when `LABTRUST_BENCH_SMOKE=1`.
- Golden suite must remain green on every run.
