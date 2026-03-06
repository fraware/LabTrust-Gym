# Changelog

All notable changes to LabTrust-Gym are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-15

### Added

- Multi-agent environment (PettingZoo/Gym style) for hospital lab automation with trust skeleton (pathology / blood sciences lane).
- RBAC, signed actions, append-only audit log, invariants, anomaly throttles driven by versioned policy and golden scenarios.
- Pipelines: deterministic, llm_offline, llm_live.
- Coordination suite (coord_scale, coord_risk) with methods including consensus_paxos_lite, swarm_stigmergy_priority, risk injections, study runner.
- UI export and viewer data contract; risk register with evidence gaps and validate-coverage --strict.
- Valid FHIR R4 export (data-absent-reason, no placeholder IDs).
- PPO/MARL baselines (train_config, obs_history_len, Optuna HPO).
- Prompt-injection defense (pre-LLM block, output consistency).
- Official benchmark pack, security attack suite, safety case, paper-ready release artifact (package-release paper_v0.1).
- Documentation: architecture, benchmarks, contracts, getting started, security, MkDocs site.

### Security

- Trust skeleton: audit log, token verification, RBAC. Production deployment and operational security are the responsibility of integrators.

[0.2.0]: https://github.com/fraware/LabTrust-Gym/releases/tag/v0.2.0
