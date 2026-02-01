# Contributing to LabTrust-Gym

## Development setup

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev]"
labtrust --version   # optional: check version + git SHA
```

## Code quality

Before opening a PR:

- `ruff format` and `ruff check`
- `mypy src/`
- `pytest -q`
- `labtrust validate-policy`

Policy files under `policy/` must validate against the JSON schemas in `policy/schemas/`. New or modified policy files must pass validation. Legacy and design-only YAML (e.g. override matrix, compiler contracts) live under `docs/design/` and are not loaded by the runtime.

## Golden suite

The golden scenarios in `policy/golden/golden_scenarios.v0.1.yaml` define correctness. Do not weaken expectations. When adding engine behaviour, extend the suite only with new scenarios or new assertions; do not relax existing ones.

## PR checklist

- New or modified policy files validated
- New emit types added to `policy/emits/emits_vocab.v0.1.yaml` (or none)
- Golden suite impact explained
- Tests added or updated

Preferred PR size: under 400 lines where practical.

## Optional smoke tests (env vars)

- **Quick-eval** — Run 1 episode each of TaskA, TaskD, TaskE: `labtrust quick-eval --seed 42` (requires `.[env,plots]`). CI runs this on every push/PR.
- **LABTRUST_BENCH_SMOKE=1** — Run benchmark smoke (1 episode per task): `labtrust bench-smoke --seed 42` (requires `.[env]`).
- **LABTRUST_REPRO_SMOKE=1** — Run reproduce smoke: `labtrust reproduce --profile minimal --out runs/repro_smoke` (requires `.[env,plots]`).
- **LABTRUST_MARL_SMOKE=1** — Run MARL smoke: `pytest tests/test_marl_smoke.py -v` (requires `.[marl]`).
- **Package-release:** `labtrust package-release --profile minimal --out /tmp/labtrust_release --seed-base 100` (requires `.[env,plots]`). Determinism: `pytest tests/test_package_release.py -v` with `LABTRUST_REPRO_SMOKE=1`.
