# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- Repo layout: `policy/` (schemas, emits, invariants, tokens, reason_codes, zones, catalogue, stability, equipment, critical, golden), `src/labtrust_gym/` (engine, policy, runner, cli), `tests/`, `examples/`, `docs/`.
- Golden runner and adapter interface: `LabTrustEnvAdapter`, `GoldenRunner`, emits vocabulary validation (unknown emits fail).
- CLI: `labtrust validate-policy` for policy/schema and emits validation.
- CI: ruff format/check, mypy, pytest, policy validation.
- Apache-2.0 license, README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.
- **docs/STATUS.md** — Current state of the repo: implemented (policy validation, hashchain, tokens, zones, specimens, QC, critical, catalogue/stability, co-location), not implemented (queueing/queue_head, GS-002; PettingZoo API; MARL/LLM baselines), and what remains.
- Engine: audit hashchain and forensic freeze (GS-022); token lifecycle and dual approval (GS-010–013); zones and doors (GS-008, GS-009, GS-020); specimen acceptance (GS-003–005, GS-021); QC and result gating (GS-014, GS-015); critical results notify/ack (GS-016–018); catalogue and stability START_RUN gating (GS-001, GS-006, GS-007); co-location device–agent zone (GS-019). Full golden suite: 21/22 scenarios pass; GS-002 fails on missing queue_head/QUEUE_RUN.

## [0.1.0] - TBD

- Initial policy-first layout and golden suite scaffolding.
- Runner output contract schema and golden scenarios (15–22 scenarios).
- Emits vocab and strict validation in runner.
