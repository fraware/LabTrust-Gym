# Contributing to LabTrust-Gym

## Development setup

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev]"
labtrust --version   # optional: check version + git SHA
```

For a full verification command sequence, see [Evaluation checklist](docs/benchmarks/evaluation_checklist.md). To test and audit the repo (lint, format, typecheck, tests, benchmarks, quick-eval, coordination, reproduce, docs), run the steps there or use `make verify`.

## Documentation

Comments and docstrings should be clear and free of unexplained jargon. See [Documentation standards](docs/reference/documentation_standards.md) for module/class/function docstrings, structure, and style. New or modified public modules, classes, or functions must have docstrings that meet those standards (module purpose, no unexplained jargon, and for functions: summary and Args/Returns where applicable). Existing code is being brought up to standard incrementally; see [Documentation mission checklist](docs/reference/documentation_mission_checklist.md).

## Code quality

Before opening a PR:

- `ruff format` and `ruff check` (lines must not exceed 120 characters; E501 is enforced). For naming exceptions (N802, N806), see [Code style and lint](docs/reference/code_style_and_lint.md).
- `mypy src/` (must pass; CI fails on type errors)
- `pytest -q`
- `labtrust validate-policy`

Policy files under `policy/` must validate against the JSON schemas in `policy/schemas/`. New or modified policy files must pass validation. Legacy and design-only YAML (e.g. override matrix, compiler contracts) live under `docs/architecture/design/` and are not loaded by the runtime.

## Testing and contracts

- **Frozen contracts:** Do not weaken runner output, queue contract, coordination interface, or risk register schema without a version bump and doc update. See [Frozen contracts](docs/contracts/frozen_contracts.md) for the canonical list.
- **Implementation audit:** What is tested vs manual checklists: see [Evaluation checklist](docs/benchmarks/evaluation_checklist.md) and [CI](docs/operations/ci.md).
- **Troubleshooting:** Common failures (verify-bundle, policy validation, pack gate, E2E chain): [Troubleshooting](docs/getting-started/troubleshooting.md).

Keep the repo root minimal: do not commit CLI or build artifacts (e.g. `results.json`, `out.json`, `bench_smoke_*.json`, `quick_eval_*/`, `site/`). Use `labtrust_runs/` or `--out <path>` for benchmark and study outputs. See [Repository structure](docs/reference/repository_structure.md).

## Golden suite

The golden scenarios in `policy/golden/golden_scenarios.v0.1.yaml` define correctness. Do not weaken expectations. When adding engine behaviour, extend the suite only with new scenarios or new assertions; do not relax existing ones.

## PR checklist

- New or modified policy files validated
- New emit types added to `policy/emits/emits_vocab.v0.1.yaml` (or none)
- Golden suite impact explained
- Tests added or updated
- New or modified public functions/methods have docstrings in Google style (summary + Args/Returns/Raises where applicable)

Preferred PR size: under 400 lines where practical.

Before **tagging a release**, run the full E2E artifacts chain and ensure it passes (package-release → export-risk-register into release dir → build-release-manifest → verify-release --strict-fingerprints → schema/crosswalk). See [Release checklist](docs/operations/release_checklist.md).

## Optional smoke tests (env vars)

- **Quick-eval** — Run 1 episode each of throughput_sla, adversarial_disruption, multi_site_stat: `labtrust quick-eval --seed 42` (requires `.[env,plots]`). CI runs this on every push/PR.
- **LABTRUST_BENCH_SMOKE=1** — Run benchmark smoke (1 episode per task): `labtrust bench-smoke --seed 42` (requires `.[env]`).
- **LABTRUST_REPRO_SMOKE=1** — Run reproduce smoke: `labtrust reproduce --profile minimal --out runs/repro_smoke` (requires `.[env,plots]`).
- **Coordination tests** — Run all coordination-related tests: `pytest -q tests/ -k coordination` (requires `.[env]`). CI coordination-smoke job (when `LABTRUST_COORDINATION_SMOKE=1`) runs validate-policy, these tests, and one-episode coord_scale + coord_risk. See [Coordination methods](docs/coordination/coordination_methods.md) (Coordination done checklist section).
- **LABTRUST_PAPER_SMOKE=1** — Run package-release paper profile smoke (1 episode baselines, 2 episodes insider_key_misuse study): `labtrust package-release --profile paper_v0.1 --seed-base 100 --out /tmp/paper_smoke` (requires `.[env,plots]`). Determinism: `pytest tests/test_package_release.py -v` (includes paper_v0.1 smoke and CLI test).
- **LABTRUST_MARL_SMOKE=1** — Run MARL smoke: `pytest tests/test_marl_smoke.py -v` (requires `.[marl]`).
- **Package-release:** `labtrust package-release --profile minimal --out /tmp/labtrust_release --seed-base 100` (requires `.[env,plots]`). For paper-ready artifact: `--profile paper_v0.1` (see [Paper provenance](docs/benchmarks/paper/README.md) and [Release checklist](docs/operations/release_checklist.md)). Determinism: `pytest tests/test_package_release.py -v` with `LABTRUST_REPRO_SMOKE=1` for minimal/full; paper_v0.1 tests use `LABTRUST_PAPER_SMOKE=1`.
