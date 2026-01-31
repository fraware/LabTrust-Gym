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

## Layout

- `policy/` — Versioned YAML/JSON: `schemas/` (JSON schemas for all policy files), emits vocab, invariants, tokens, reason codes, zones, catalogue, stability, equipment, critical, golden scenarios. All policy files are validated against their schemas by `labtrust validate-policy`.
- `src/labtrust_gym/` — Package: `engine/` (core_env, audit_log, zones, specimens, qc, critical, queueing, devices, clock, rng, catalogue_runtime, tokens_runtime), `policy/` (loader, validate, emits, tokens, reason_codes), `runner/` (golden runner, adapter, emits validator), `envs/` (PettingZoo Parallel and AEC wrappers), `baselines/` (scripted_ops, scripted_runner), `benchmarks/` (tasks, metrics, runner), `logging/` (episode log), `cli/`.
- `tests/` — Pytest: golden suite, policy validation (including invalid-policy-fails), hashchain, tokens, zones, specimens, qc, critical, stability, catalogue, queueing, devices_timing, scripted_ops, scripted_runner, PZ parallel/AEC smoke, benchmark smoke, episode log.
- `examples/` — `minimal_random_policy_agent.py`, `scripted_ops_agent.py`, `scripted_runner_agent.py`.
- `docs/` — Architecture, policy pack, threat model, invariants, benchmarks, CI, PettingZoo API, queue contract; **`docs/STATUS.md`** — current state: what’s implemented and what remains.

## Golden runner

The golden runner (`labtrust_gym.runner`) runs scenario scripts from `policy/golden/golden_scenarios.v0.1.yaml` against an environment adapter. The adapter must implement `LabTrustEnvAdapter` (reset, step, query). Step results must conform to the runner output contract (status, emits, violations, hashchain, etc.). Unknown emits fail the suite. With the real engine the full golden suite passes: `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`.

## Current state

See **`docs/STATUS.md`** for a detailed report: what is implemented (policy validation, hashchain, tokens, zones, specimens, QC, critical results, catalogue/stability, co-location, queueing, PettingZoo Parallel wrapper), and what remains.

## License

Apache-2.0.
