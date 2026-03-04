# System overview: how the pieces fit together

This document gives a single narrative of how LabTrust-Gym is layered and how the main components interact. For detailed specs and contracts, see [Architecture](architecture.md), [Frozen contracts](../contracts/frozen_contracts.md), and the linked docs below.

## Layering

| Layer | Location | Role |
|-------|----------|------|
| **Policy** | `policy/` | Versioned YAML/JSON: zones, RBAC, keys, invariants, golden scenarios, coordination methods, risk registry, security suite. Validated by `labtrust validate-policy` (schema and structural validity only; does not check logical correctness). |
| **Engine** | `engine/` | Core simulator: `CoreEnv` (reset, step, query). Implements `LabTrustEnvAdapter`. No PettingZoo. |
| **Envs** | `envs/` | PettingZoo Parallel (and AEC) wrappers over the engine; observations, actions, rewards, infos. |
| **Baselines** | `baselines/` | Who chooses actions: scripted ops, scripted runner, adversary, insider, LLM agent, coordination methods. |
| **Benchmarks** | `benchmarks/` | Task definitions, metrics, and the **runner** that owns the env and drives the step loop. |
| **Studies / Export / Security** | `studies/`, `export/`, `benchmarks/security_runner.py` | Studies run many (scale × method × injection) cells; export builds the risk-register bundle; security runs the attack suite. |

The **benchmark runner owns the env**. Baselines and coordination methods never call the env; they only receive observations and infos and return action dicts. See [Coordination and env data flow](../coordination/coordination_and_env.md).

## Where the env comes from

When you run a benchmark (`run-benchmark`, `quick-eval`, or a study that calls the runner):

1. **Domain adapter** — The runner resolves a domain by ID (default `hospital_lab`) via `get_domain_adapter_factory(domain_id)`. The factory returns a `LabTrustEnvAdapter` (for the lab, that is `CoreEnv()`). See [Workflow and domain spec](workflow_domain_spec.md).
2. **Engine** — Each episode the runner creates the engine via that adapter (e.g. `CoreEnv()`).
3. **PZ wrapper** — The runner wraps the engine in `LabTrustParallelEnv` (`envs/pz_parallel.py`), which exposes the PettingZoo Parallel API and the `BenchmarkEnv` protocol.

So the chain is: **domain adapter → CoreEnv → LabTrustParallelEnv**. The runner only talks to the PZ/BenchmarkEnv interface; it does not call the engine directly. Custom domains can be registered via the `labtrust_gym.domains` entry point; see [Extension development](../agents/extension_development.md).

## Per-step data flow (one episode)

For each step in an episode, the benchmark runner does:

1. **Observations** — From the previous `env.step` (or `env.reset` on step 0).
2. **Optional: mutate observations** — If a risk injector is present (e.g. for `coord_risk`), `risk_injector.mutate_obs(obs)` can alter what decision-makers see.
3. **Action choice** — With coordination: `coord_method.step(context)` or `coord_method.propose_actions(obs, infos, t)` returns one action dict per agent. Without coordination: each scripted (or LLM) agent in `scripted_agents_map` returns an action; the runner assembles the action dict.
4. **Optional: mutate actions** — If a risk injector is present, `risk_injector.mutate_actions(actions_dict)` can alter actions before they are sent to the env.
5. **Env step** — The runner converts action dicts to `(actions, action_infos)` per the [Action contract](../contracts/frozen_contracts.md#action-contract-v01) and calls **`env.step(actions, action_infos)`**. Only the runner calls `env.step`.

Full detail: [Coordination and env data flow](../coordination/coordination_and_env.md).

## Golden runner vs benchmark runner

| | Golden runner | Benchmark runner |
|--|----------------|------------------|
| **Purpose** | Correctness backbone: assert that the engine obeys the step contract and golden scenarios. | Run N episodes per task, collect metrics, write results and logs. |
| **Env** | Uses a `LabTrustEnvAdapter` directly (e.g. `PZParallelAdapter` over `CoreEnv`). Does **not** use PettingZoo. | Uses `LabTrustParallelEnv` (PZ) over the engine; full stack with baselines, optional coordination, optional risk injectors. |
| **Input** | Golden scenarios from `policy/golden`. | Task (e.g. `throughput_sla`, `coord_risk`), seed, optional coord method and injection. |
| **Output** | Pass/fail per scenario; unknown emits cause assertion failure. | `results.json`, episode logs, optional `coord_decisions.jsonl`. |

Both use the same core engine; the golden runner checks it in isolation, the benchmark runner exercises it through the full pipeline.

## Policy at runtime

Initial state for each episode comes from the task (`task.get_initial_state(seed, policy_root)`), and can include `policy_root` and optional `effective_policy` (e.g. from a partner overlay). Inside `core_env.reset()`, **policy resolution** (`engine/policy_resolution.py`) decides each policy value: use `effective_policy[key]` if present and valid, else load from `policy_root` (e.g. RBAC, keys, zones, invariants), else use a default. So the order is: **effective_policy over file over default**. That keeps scenario overrides and file-based policy in one place.

## CLI to components

| CLI command (or flow) | Main components involved |
|------------------------|---------------------------|
| `validate-policy` | `policy/loader`, `policy/validate`, `policy/schemas/` |
| `run-benchmark`, `quick-eval` | `get_task()` → `run_benchmark()` → `env_factory`, `scripted_agents_map` or `coord_method`, optional `risk_injector` → per episode: `run_episode()` (simulation-centric) or `run_episode_agent_driven()` (agent-centric when `--agent-driven`). Simulation-centric: obs → mutate_obs → coord/agents → mutate_actions → env.step. Agent-centric: driver holds env; agent calls step_lab tool to step. |
| `run-coordination-study` | `coordination_study_runner` → `run_benchmark()` per (scale × method × injection) cell |
| `run-security-suite` | `security_runner` → attack suite from policy → `SECURITY/attack_results.json` |
| `export-risk-register` | `export/risk_register_bundle` → policy + run dirs → `RISK_REGISTER_BUNDLE.v0.1.json` |
| `validate-coverage --strict` | Risk register bundle + `required_bench_plan` + waivers → exit 1 if required risk has missing evidence |
| `package-release` | `official_pack` → baselines, SECURITY/, SAFETY_CASE/, transparency log into one output tree |
| Golden suite (e.g. `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py`) | `golden_runner` → `LabTrustEnvAdapter`, scenarios from `policy/golden` |

## Simulation, LLMs, and agentic systems

The **benchmark runner** owns the PettingZoo env (LabTrustParallelEnv) in the default (simulation-centric) mode. Optionally, **agent-driven mode** (`run-benchmark --agent-driven`) uses a driver that holds the env; the agent calls a step_lab tool to advance it, so the agent drives the loop. LLM agents and LLM-based (including agentic) coordination methods are **policies**: they receive observations and return actions; in simulation-centric mode only the runner calls `env.step`; in agent-driven mode only the driver calls `env.step` when the agent invokes step_lab. The security suite uses the PZ env only for **coord_pack_ref** (system-level coordination-under-attack); agent/shield tests (scenario_ref, llm_attacker) use synthetic observations and do not run the env. For a full breakdown and table, see [Simulation, LLMs, and agentic systems](simulation_llm_agentic.md).

## See also

- [Architecture](architecture.md) — Component list and CLI summary.
- [Architecture diagrams](diagrams.md) — Mermaid pipeline and lab topology.
- [Coordination and env data flow](../coordination/coordination_and_env.md) — Per-step flow and contracts.
- [Repository structure](../reference/repository_structure.md) — Directory layout and where outputs go.
- [Frozen contracts](../contracts/frozen_contracts.md) — Runner output, action contract, BenchmarkEnv, coordination contract.
- [Simulation, LLMs, and agentic systems](simulation_llm_agentic.md) — PettingZoo vs LLM vs agentic; when the PZ env is used.
