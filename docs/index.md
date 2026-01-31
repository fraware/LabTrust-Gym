# LabTrust-Gym

A multi-agent environment (PettingZoo/Gym style) for a self-driving hospital lab, with a reference **trust skeleton**: RBAC, signed actions, append-only audit log, invariants, and anomaly throttles.

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

With PettingZoo, benchmarks, and plots:

```bash
pip install -e ".[dev,env,plots]"
LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q
labtrust run-benchmark --task TaskA --episodes 5 --seed 42 --out results.json
labtrust reproduce --profile minimal
```

Optional extras: `.[env]` (PettingZoo/Gymnasium), `.[plots]` (matplotlib), `.[marl]` (Stable-Baselines3), `.[docs]` (MkDocs + mkdocstrings).

## CLI summary

| Command | Description |
|---------|-------------|
| `validate-policy` | Validate all policy files against JSON schemas |
| `run-benchmark` | Run TaskA / TaskB / TaskC / TaskD, write results.json |
| `bench-smoke` | 1 episode per task (TaskA, TaskB, TaskC) |
| `run-study` | Run study from spec (ablations → conditions) |
| `make-plots` | Generate figures and data tables from a study run |
| `reproduce --profile minimal \| full` | Reproduce minimal results + figures (TaskA & TaskC sweep + plots) |
| `train-ppo`, `eval-ppo` | PPO training/eval (requires `.[marl]`) |

## Layout

| Path | Description |
|------|-------------|
| `policy/` | Versioned YAML/JSON: schemas, emits, invariants (registry v1.0), tokens, reason_codes, zones, catalogue, stability, equipment, critical, enforcement, studies, llm, golden. Validated by `labtrust validate-policy`. |
| `src/labtrust_gym/` | Package: `engine/` (core_env, audit_log, zones, specimens, qc, critical, queueing, devices, invariants_runtime, enforcement, …), `policy/` (loader, validate, invariants_registry), `runner/`, `envs/` (PettingZoo), `baselines/` (scripted_ops, scripted_runner, adversary, llm, marl), `benchmarks/`, `studies/` (study_runner, plots, reproduce), `logging/`, `cli/`. |
| `tests/` | Pytest: golden suite, policy validation, hashchain, tokens, zones, specimens, qc, critical, queueing, benchmarks, invariant registry, enforcement, study runner, plots, reproduce smoke, adversary, marl smoke, llm agent mock. |
| `docs/` | Architecture, policy pack, invariants & enforcement, benchmarks, studies, reproduce, PettingZoo API, CI, threat model, MARL/LLM baselines, STATUS. MkDocs site (build with `.[docs]`). |

## What's frozen

Contracts and schema versions that define correctness (anti-regression backbone): **[Frozen contracts](frozen_contracts.md)** — runner output contract, queue contract (v0.1), invariant registry schema (v1.0), enforcement map schema (v0.1), study spec schema (v0.1).

## See also

- [Architecture](architecture.md)
- [Policy pack and schemas](policy_pack.md)
- [Frozen contracts](frozen_contracts.md) (canonical list)
- [Invariants and enforcement](invariants_registry.md) · [Enforcement](enforcement.md)
- [PettingZoo API](pettingzoo_api.md)
- [Benchmarks](benchmarks.md) · [Studies and plots](studies.md) · [Reproduce (minimal results + figures)](reproduce.md)
- [MARL baselines](marl_baselines.md) · [LLM baselines](llm_baselines.md)
- [API Reference](api/index.md) (auto-generated)
