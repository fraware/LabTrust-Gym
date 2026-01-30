# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- Repo layout: `policy/` (schemas, emits, invariants, tokens, reason_codes, zones, catalogue, stability, equipment, golden), `src/labtrust_gym/` (engine, policy, runner, cli), `tests/`, `examples/`, `docs/`.
- Golden runner and adapter interface: `LabTrustEnvAdapter`, `GoldenRunner`, emits vocabulary validation (unknown emits fail).
- CLI: `labtrust validate-policy` for policy/schema and emits validation.
- CI: ruff format/check, mypy, pytest, policy validation.
- Apache-2.0 license, README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.

## [0.1.0] - TBD

- Initial policy-first layout and golden suite scaffolding.
- Runner output contract schema and golden scenarios (15–22 scenarios).
- Emits vocab and strict validation in runner.
