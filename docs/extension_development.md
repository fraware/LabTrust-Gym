# Extension development guide

This guide describes how to extend LabTrust-Gym with your own domains, coordination methods, tasks, invariant handlers, security/safety suites, and metrics without forking the core repository.

## Overview

The core exposes **registries** and optional **setuptools entry_points**. You can either:

- **Register at runtime**: import the registry and call `register_*` from your code (e.g. in your test suite or runner).
- **Register via entry_points**: ship a pip-installable package that declares entry_points; when `labtrust` runs, plugins are loaded and your extensions are registered.

## Policy root and paths

- Policy is loaded from a **policy root** (repo root or `LABTRUST_POLICY_DIR`). Use `labtrust_gym.config.get_repo_root()` and `labtrust_gym.config.policy_path(policy_root, *parts)` to build paths under `policy/`.
- A **lab profile** (`policy/lab_profiles/<id>.v0.1.yaml`) can set `partner_id`, provider IDs, and paths. Use `labtrust --profile <id> <command>` to apply it.

## Registries and APIs

| Extension | Register function | Entry-point group | Notes |
|-----------|-------------------|-------------------|--------|
| Domain | `labtrust_gym.domain.registry.register_domain(id, factory)` | `labtrust_gym.domains` | `factory(workflow_spec, config) -> LabTrustEnvAdapter`; use `get_domain_adapter_factory(domain_id)` to resolve, `list_domains()` for known IDs. Default domain is `hospital_lab`; a profile field `domain_id` or future `--domain` can override when the runner uses the registry. |
| Coordination method | `labtrust_gym.baselines.coordination.registry.register_coordination_method(method_id, factory)` | `labtrust_gym.coordination_methods` | `factory(policy, repo_root, scale_config, params) -> CoordinationMethod` |
| Task | `labtrust_gym.benchmarks.tasks.register_task(name, task_class)` | `labtrust_gym.tasks` | `task_class` must be a subclass of `BenchmarkTask` |
| Invariant handler | `labtrust_gym.engine.invariants_runtime.register_invariant_handler(logic_type, check_name, handler)` | `labtrust_gym.invariant_handlers` | Key format: `type.check_name` (e.g. `state.custom_check`). Handler signature: `(env, event, params) -> (passed, reason_code, details) \| None` |
| Security suite | `labtrust_gym.benchmarks.security_runner.register_security_suite_provider(provider_id, provider)` | `labtrust_gym.security_suite_providers` | Provider: `load_suite(policy_root, partner_id) -> dict`, `run_suite(policy_root, repo_root, ...) -> list[dict]`. Resolve with `get_security_suite_provider(id)`; list IDs with `list_security_suite_providers()`. |
| Safety case | `labtrust_gym.security.safety_case.register_safety_case_provider(provider_id, provider)` | `labtrust_gym.safety_case_providers` | Provider: `load_claims(policy_root) -> dict`, `build_safety_case(policy_root) -> dict`. Resolve with `get_safety_case_provider(id)`; list IDs with `list_safety_case_providers()`. |
| Metrics aggregator | `labtrust_gym.benchmarks.metrics.register_metrics_aggregator(aggregator_id, aggregator)` | `labtrust_gym.metrics_aggregators` | Same signature as `compute_episode_metrics`. Resolve with `get_metrics_aggregator(id)`; list IDs with `list_metrics_aggregators()`. |
| Benchmark pack loader | `labtrust_gym.benchmarks.official_pack.register_benchmark_pack_loader(loader_id, loader)` | `labtrust_gym.benchmark_pack_loaders` | Loader: `(repo_root, prefer_v02, partner_id) -> (pack_dict, version, path)`; use `load_benchmark_pack(..., loader_id=...)` to select. |

## Entry-point format

In your package `pyproject.toml`:

```toml
[project.entry-points."labtrust_gym.tasks"]
my_task = "mylab.tasks:MyBenchmarkTask"

[project.entry-points."labtrust_gym.coordination_methods"]
my_method = "mylab.coordination:my_factory"

[project.entry-points."labtrust_gym.invariant_handlers"]
state.my_check = "mylab.invariants:check_my_custom"
```

- **labtrust_gym.domains**: `id = module:factory_callable`
- **labtrust_gym.coordination_methods**: `method_id = module:factory_func`
- **labtrust_gym.tasks**: `task_name = module:TaskClass` (class, not instance)
- **labtrust_gym.invariant_handlers**: `type.check_name = module:handler_func`
- **labtrust_gym.security_suite_providers**: `provider_id = module:provider_or_factory`
- **labtrust_gym.safety_case_providers**: `provider_id = module:provider_or_factory`
- **labtrust_gym.metrics_aggregators**: `aggregator_id = module:aggregator_callable`
- **labtrust_gym.benchmark_pack_loaders**: `loader_id = module:loader_callable` (signature: `(repo_root, prefer_v02, partner_id) -> (pack_dict, version, path)`)

Plugins are loaded when the CLI starts (`labtrust`). For programmatic use, call `labtrust_gym.plugins.load_plugins()` once before using registries.

## Contracts

Extensions must conform to existing contracts:

- **Domains**: implement `LabTrustEnvAdapter` (reset, step, query); step return shape must satisfy the runner output contract.
- **Coordination methods**: implement `CoordinationMethod` (reset, propose_actions with action_index 0..5).

### Coordination method factory contract

The factory registered with `register_coordination_method(method_id, factory)` or via the `labtrust_gym.coordination_methods` entry_point must have this exact signature:

```text
factory(policy: dict[str, Any], repo_root: Path | None, scale_config: dict[str, Any] | None, params: dict[str, Any]) -> CoordinationMethod
```

- `params` includes merged default_params from `policy/coordination/coordination_methods.v0.1.yaml` and any kwargs passed by the runner (e.g. `compute_budget`, `pz_to_engine`, `proposal_backend`). The `method_id` in YAML must match a registered factory (built-in or plugin).
- **Tasks**: subclass `BenchmarkTask`; provide name, max_steps, scripted_agents, get_initial_state, reward_config.
- **Invariant handlers**: return `(passed: bool, reason_code: str | None, details: dict | None) | None`; logic_template in registry YAML uses `type` and `parameters.check`.
- **Results**: custom metrics may add keys to episode.metrics; results v0.3 allows optional fields. The CI-stable subset (v0.2) remains fixed.

See [Frozen contracts](frozen_contracts.md) and [Metrics contract](metrics_contract.md).

## Lab profile

Create `policy/lab_profiles/<profile_id>.v0.1.yaml`:

```yaml
version: "0.1"
profile_id: my_lab
description: "My organization lab."
partner_id: my_partner
security_suite_provider_id: default
safety_case_provider_id: default
metrics_aggregator_id: default
extension_packages: ["mylab_labtrust"]
```

Then run: `labtrust --profile my_lab run-benchmark --task throughput_sla --episodes 5`. The profile overrides `partner_id` and optional provider IDs.

## Packaging a lab extension

1. Create a package (e.g. `mylab_labtrust`) that depends on `labtrust-gym`.
2. Implement your domain/tasks/coordination/invariant handlers/providers.
3. Register them in your package root or in a `register()` function that you call from entry_points. For entry_points, point to the class or factory; the core will call the appropriate `register_*`.
4. Optionally ship a policy bundle (your `policy/` or a subset) and document `LABTRUST_POLICY_DIR` or use a lab profile that points to it.
5. Users install your package and run `labtrust`; your entry_points are loaded automatically.

## See also

- [Forker guide](FORKER_GUIDE.md) for policy-only customization (partner overlay, coordination methods YAML, risk register).
- [Frozen contracts](frozen_contracts.md) for the extensibility section and schema stability.
