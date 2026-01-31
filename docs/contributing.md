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

## Optional smoke tests (env vars)

- **LABTRUST_BENCH_SMOKE=1** — Benchmark smoke: `labtrust bench-smoke --seed 42` (requires `.[env]`).
- **LABTRUST_REPRO_SMOKE=1** — Reproduce smoke: `labtrust reproduce --profile minimal --out runs/repro_smoke` (requires `.[env,plots]`).
- **LABTRUST_MARL_SMOKE=1** — MARL smoke: `pytest tests/test_marl_smoke.py -v` (requires `.[marl]`).
