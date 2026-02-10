# Contributing

See the repository [CONTRIBUTING.md](https://github.com/fraware/LabTrust-Gym/blob/main/CONTRIBUTING.md) for full guidelines. Summary:

## Development setup

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev]"
```

## Code quality

Before opening a PR:

- `ruff format` and `ruff check`
- `mypy src/`
- `pytest -q`
- `labtrust validate-policy`

Policy files under `policy/` must validate against the JSON schemas in `policy/schemas/`.

## Golden suite

The golden scenarios in `policy/golden/golden_scenarios.v0.1.yaml` define correctness. Do not weaken expectations. When adding engine behaviour, extend the suite only with new scenarios or new assertions.

## PR checklist

- New or modified policy files validated
- New emit types added to `policy/emits/emits_vocab.v0.1.yaml` (or none)
- Golden suite impact explained
- Tests added or updated

Preferred PR size: under 400 lines where practical.

## Verification and audit (full command sequence)

To fully audit the repo as a new user, run in order from the repo root:

1. **Install and sanity:** `pip install -e ".[dev]"`, `labtrust --version`, `labtrust validate-policy` (optional: `--partner hsl_like`).
2. **Lint and format:** `ruff format .`, `ruff format --check .`, `ruff check .`.
3. **Type check:** `mypy src/`.
4. **Core tests:** `pytest -q` (or exclude PZ/benchmark smoke per CI). Golden suite: `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q`.
5. **Env and plots:** `pip install -e ".[dev,env,plots]"`.
6. **Quick-eval and benchmarks:** `labtrust quick-eval --seed 42`, `labtrust bench-smoke --seed 42` (if LABTRUST_BENCH_SMOKE=1).
7. **Reproduce:** `labtrust reproduce --profile minimal --out runs/repro_smoke` (if LABTRUST_REPRO_SMOKE=1).
8. **Package release and verify:** `labtrust package-release --profile minimal --seed-base 100 --out <dir>`, then `labtrust verify-release --release-dir <dir>`, then `labtrust export-risk-register --out <dir2> --runs <dir>` (or use `make e2e-artifacts-chain`).

On Windows use PowerShell; avoid paths with accented characters. See [Installation](installation.md), [CI](ci.md), and [Troubleshooting](troubleshooting.md) for details and common failures.

## Optional smoke tests (env vars)

- **Quick-eval** — `labtrust quick-eval --seed 42` (1 episode throughput_sla, adversarial_disruption, multi_site_stat; requires `.[env,plots]`). CI runs this on every push/PR.
- **LABTRUST_BENCH_SMOKE=1** — Benchmark smoke: `labtrust bench-smoke --seed 42` (requires `.[env]`).
- **LABTRUST_REPRO_SMOKE=1** — Reproduce smoke: `labtrust reproduce --profile minimal --out runs/repro_smoke` (requires `.[env,plots]`).
- **LABTRUST_MARL_SMOKE=1** — MARL smoke: `pytest tests/test_marl_smoke.py -v` (requires `.[marl]`).
