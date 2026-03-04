# Public API

This page lists the **stable surface** intended for external use. Use these entry points and contracts when building extensions or integrating with LabTrust-Gym programmatically. Other modules may change without notice.

## CLI

All subcommands of `labtrust` are part of the public API. See the [CLI output contract](../contracts/cli_contract.md) for exit codes, minimal smoke args, and output paths. Commands are listed in the [README](https://github.com/fraware/LabTrust-Gym/blob/main/README.md#cli) and smoke-tested in `tests/test_cli_smoke_matrix.py`.

## Programmatic entry points

| Symbol | Module | Description |
|--------|--------|-------------|
| `run_security_suite` | `labtrust_gym.benchmarks.security_runner` | Run the security attack suite; returns list of result dicts. |
| `run_suite_and_emit` | `labtrust_gym.benchmarks.security_runner` | Run the suite and write SECURITY/ artifacts to disk. |
| `run_coordination_security_pack` | `labtrust_gym.studies.coordination_security_pack` | Run the coordination security pack (full PZ env + coordination + injectors); writes pack_results/, pack_gate.md, SECURITY/. |
| `run_episode` | `labtrust_gym.benchmarks.runner` | Run one episode (task, seed, env_factory, optional coord_method, risk_injector); returns (metrics_dict, step_results_per_step). Simulation-centric only. |
| `run_episode_agent_driven` | `labtrust_gym.benchmarks.agent_driven_driver` | Run one episode in agent-centric mode: backend runs until driver is done; agent calls step_lab to advance the env. Same return shape as run_episode. |
| `run_benchmark` | `labtrust_gym.benchmarks.runner` | Run benchmark for a task (multiple episodes); used by CLI `run-benchmark`. Supports `agent_driven=True` (or CLI `--agent-driven`) for agent-centric mode; then calls run_episode_agent_driven per episode. |
| `load_attack_suite` | `labtrust_gym.benchmarks.security_runner` | Load security_attack_suite.v0.1.yaml from policy root; returns dict with attacks, controls, version. |
| `validate_policy` | `labtrust_gym.policy.validate` | Validate all policy files against schemas; returns list of error strings (empty if valid). |
| `get_repo_root` | `labtrust_gym.config` | Resolve policy root (repo root or LABTRUST_POLICY_DIR). |
| `policy_path` | `labtrust_gym.config` | Build path under policy/ from policy root and parts. |

For run-benchmark-style flows without the CLI, use `run_benchmark` or the same code path the CLI uses (see `labtrust_gym.cli.main`). Two orchestration modes: default is simulation-centric (runner steps env each tick); pass `agent_driven=True` (or `--agent-driven` on CLI) for agent-centric mode (agent calls step_lab to advance the env). See [Simulation, LLMs, and agentic systems](../architecture/simulation_llm_agentic.md).

## Contracts (implement these for extensions)

Implement these protocols and types when extending the platform:

| Contract | Location | Purpose |
|----------|----------|---------|
| **BenchmarkEnv** | `labtrust_gym.benchmarks.env_protocol` | Env interface for run_episode: agents, reset, step, get_timing_summary, get_device_queue_lengths, get_device_ids, get_zone_ids, get_dt_s, close. |
| **CoordinationMethod** | `labtrust_gym.baselines.coordination.interface` | reset(seed, policy, scale_config); propose_actions(obs, infos, t) -> dict of agent_id to action_dict (action_index 0..5). |
| **LabTrustEnvAdapter** | Used by golden runner / online server | reset, step, query; step return shape must satisfy runner output contract. |
| **Action contract** | `labtrust_gym.envs.action_contract` | Per-step action_index in 0..5; optional action_type, args, reason_code, token_refs. All coordination methods and risk injectors must use these indices. |

See [Frozen contracts](../contracts/frozen_contracts.md) for the full list of versioned contracts and schema stability.

## Registries

Register extensions via `register_*` functions or setuptools entry_point groups. Full table: [Extension development — Registries and APIs](../agents/extension_development.md#registries-and-apis). Entry-point groups: `labtrust_gym.tasks`, `labtrust_gym.coordination_methods`, `labtrust_gym.domains`, `labtrust_gym.invariant_handlers`, `labtrust_gym.security_suite_providers`, `labtrust_gym.safety_case_providers`, `labtrust_gym.metrics_aggregators`, `labtrust_gym.benchmark_pack_loaders`. Call `labtrust_gym.plugins.load_plugins()` before using registries when using the API programmatically (the CLI does this automatically).

## Internal / unstable

Do **not** rely on runner internals, engine internals, or private attributes of envs. Rely on **BenchmarkEnv** and the documented entry points above. The following are **not** part of the public API and may change without notice:

- Concrete implementations inside `labtrust_gym.engine`, `labtrust_gym.benchmarks.runner` (internal step loop, timing logic), and private attributes of env classes (e.g. `_engine`, `_device_ids`).
- Any module or symbol not listed on this page or in [Frozen contracts](../contracts/frozen_contracts.md) and [Extension development](../agents/extension_development.md).

When in doubt, use the CLI or the programmatic entry points and contracts listed here.
