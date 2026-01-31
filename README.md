# LabTrust-Gym

A multi-agent environment (PettingZoo/Gym style) for a self-driving hospital lab, with a reference trust skeleton: RBAC, signed actions, append-only audit log, invariants, and anomaly throttles.

## North star

- **Environment**: Pip-installable, standard multi-agent API (PettingZoo AEC or parallel).
- **Trust skeleton**: Roles/permissions, signed actions, hash-chained audit log, invariants, reason codes.
- **Benchmarks**: Tasks and baselines (scripted, MARL, LLM) with clear safety/throughput trade-offs.

## Principles

- **Golden scenarios drive development**: The simulator is correct when the golden suite passes.
- **Policy is data**: Invariants, tokens, reason codes, catalogue, zones live in versioned files under `policy/`.
- **Determinism**: Golden runs are deterministic (seeded RNG, no ambient randomness).
- **No silent failure**: Missing hooks or invalid data fail loudly with reason codes.

## Quick start

```bash
git clone https://github.com/fraware/LabTrust-Gym.git
cd LabTrust-Gym
pip install -e ".[dev]"
labtrust validate-policy
pytest -q
```

For benchmarks, studies, and plots (PettingZoo + matplotlib):

```bash
pip install -e ".[dev,env,plots]"
labtrust run-benchmark --task TaskA --episodes 5 --out results.json
labtrust reproduce --profile minimal
```

Optional extras: `.[env]` (PettingZoo/Gymnasium), `.[plots]` (matplotlib), `.[marl]` (Stable-Baselines3), `.[docs]` (MkDocs + mkdocstrings).

## CLI

- **validate-policy** — Validate all policy YAML/JSON against schemas.
- **run-benchmark** — Run TaskA, TaskB, TaskC, or TaskD; write results.json (`--task`, `--episodes`, `--out`).
- **bench-smoke** — 1 episode per task (TaskA, TaskB, TaskC).
- **run-study** — Run study from spec (`--spec`, `--out`); ablations → conditions → results.
- **make-plots** — Generate figures and data tables from a study run (`--run`).
- **reproduce** — Reproduce minimal results + figures: TaskA & TaskC sweep + plots (`--profile minimal | full`, optional `--out`).
- **train-ppo**, **eval-ppo** — PPO training/eval (requires `.[marl]`).

## Layout

- **policy/** — Versioned YAML/JSON: `schemas/`, `emits/`, `invariants/` (registry v1.0), `tokens/`, `reason_codes/`, `zones/`, `catalogue/`, `stability/`, `equipment/`, `critical/`, `enforcement/`, `studies/`, `llm/`, `golden/`. Validated by `labtrust validate-policy`.
- **src/labtrust_gym/** — `engine/` (core_env, audit_log, zones, specimens, qc, critical, queueing, devices, clock, rng, catalogue_runtime, tokens_runtime, invariants_runtime, enforcement), `policy/` (loader, validate, emits, tokens, reason_codes, invariants_registry), `runner/`, `envs/` (PettingZoo Parallel and AEC), `baselines/` (scripted_ops, scripted_runner, adversary, llm, marl), `benchmarks/`, `studies/` (study_runner, plots, reproduce), `logging/`, `cli/`.
- **tests/** — Golden suite, policy validation, hashchain, tokens, zones, specimens, qc, critical, queueing, benchmarks, invariant registry, enforcement, study runner, plots, reproduce smoke, adversary, marl smoke, llm agent mock.
- **examples/** — `minimal_random_policy_agent.py`, `scripted_ops_agent.py`, `scripted_runner_agent.py`, `llm_agent_mock_demo.py`.
- **docs/** — Architecture, policy pack, invariants & enforcement, benchmarks, studies, reproduce, PettingZoo API, CI, threat model, MARL/LLM baselines; **docs/STATUS.md** — current state. MkDocs site (build with `.[docs]`).

## Golden runner

The golden runner (`labtrust_gym.runner`) runs scenario scripts from `policy/golden/golden_scenarios.v0.1.yaml` against an environment adapter. The adapter must implement `LabTrustEnvAdapter` (reset, step, query). Step results must conform to the runner output contract (status, emits, violations, hashchain, etc.). Unknown emits fail the suite. With the real engine the full golden suite passes: `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`.

## Current state

See **docs/STATUS.md** for a detailed report: policy validation, hashchain, tokens, zones, specimens, QC, critical results, catalogue/stability, co-location, queueing, invariant registry, enforcement, PettingZoo wrappers, scripted/adversary/LLM/MARL baselines, TaskA–TaskD, studies (run-study, make-plots, reproduce), and docs site (MkDocs + API reference).

## License

Apache-2.0.
