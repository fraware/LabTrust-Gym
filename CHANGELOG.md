# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- Repo layout: `policy/` (schemas for all policy files, emits, invariants, tokens, reason_codes, zones, catalogue, stability, equipment, critical, golden), `src/labtrust_gym/` (engine, policy, runner, envs, baselines, benchmarks, logging, cli), `tests/`, `examples/`, `docs/`.
- Golden runner and adapter interface: `LabTrustEnvAdapter`, `GoldenRunner`, emits vocabulary validation (unknown emits fail). Full golden suite passes with real engine.
- CLI: `labtrust validate-policy` (all policy files validated against JSON schemas), `labtrust run-benchmark`, `labtrust bench-smoke`.
- CI: ruff format/check, mypy, pytest, policy validation; optional bench-smoke (nightly/manual).
- Apache-2.0 license, README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.
- **docs/STATUS.md** — Current state: policy schemas (emits, zones, reason_codes, tokens, dual_approval, critical, equipment, golden), hashchain, tokens, zones, specimens, QC, critical, catalogue/stability, co-location, queueing, devices/clock/rng, PettingZoo Parallel/AEC, scripted baselines, benchmark harness, episode logging.
- JSON schemas for all policy YAML/JSON (emits vocab, zones, reason codes, token registry, dual approval, critical thresholds, equipment registry, golden scenarios); wired into `validate-policy`; tests for invalid policy failing.
- Engine: audit hashchain and forensic freeze (GS-022); token lifecycle and dual approval (GS-010–013); zones and doors (GS-008, GS-009, GS-020); specimen acceptance (GS-003–005, GS-021); QC and result gating (GS-014, GS-015); critical results notify/ack (GS-016–018); catalogue and stability START_RUN gating (GS-001, GS-006, GS-007); co-location (GS-019); queueing QUEUE_RUN/queue_head/START_RUN consume (GS-002); equipment timing (devices, clock, rng; timing_mode explicit/simulated).
- PettingZoo Parallel and AEC wrappers (`envs/pz_parallel.py`, `envs/pz_aec.py`); scripted ops and scripted runner baselines; benchmark tasks (TaskA, TaskB, TaskC), metrics, runner; episode logging (JSONL).

## [0.1.0] - TBD

- Initial policy-first layout and golden suite scaffolding.
- Runner output contract schema and golden scenarios (15–22 scenarios).
- Emits vocab and strict validation in runner.
