# Simulation, LLMs, and agentic systems

This document explains how **PettingZoo** (the simulation), **large language models** (LLMs), and **agentic systems** (LLM + tool-call loops) fit together in LabTrust-Gym. It is the single reference for "who owns the env," "who feeds the LLM," and "when is the PZ env used."

## Two orchestration modes

LabTrust-Gym supports two modes; **simulation-centric** is the default.

| Mode | Who drives the loop | When time advances | How to select |
|------|---------------------|--------------------|---------------|
| **Simulation-centric** (default) | The benchmark runner. Each tick it gets obs, calls the policy (scripted or coord method), then calls `env.step`. | Every tick. | Default; no flag. |
| **Simulation-centric at scale** (N > N_max) | Runner collects one submission per agent (from scripted_agents_map or NOOP), calls `coord_method.combine_submissions(submissions, obs, infos, t)`, then `env.step`. No single coordinator outputting N actions. | Every tick. | Same as simulation-centric; `coord_propose_actions_max_agents` (default 50) in scale_config. |
| **Agent-centric** (single driver) | A single driver agent (LLM). The agent calls `step_lab(proposal)`; the driver runs `env.step` and returns obs/rewards/done. | Only when the agent calls `step_lab`. | `run-benchmark --agent-driven --coord-method <method>`. |
| **Agent-centric** (multi-agentic) | N agent backends each call `submit_my_action` (or `submit_bid` for auction); when all have submitted (or timeout), driver calls `coord_method.combine_submissions` then `env.step`. | When the driver advances the step after collecting submissions. | `run-benchmark --agent-driven --multi-agentic --coord-method <method>`. Optional `--use-parallel-multi-agentic` (with scale task + LLM): ParallelMultiAgenticBackend runs N agents in parallel per round with shared rate limiter; round_timeout_s and max_workers configurable (see [Scale operational limits](../benchmarks/scale_operational_limits.md)). |

Same env (BenchmarkEnv), same action shape, and same safety (shield, RBAC, risk injector) in both modes. Agent-centric is implemented by an additive driver (`src/labtrust_gym/benchmarks/agent_driven_driver.py`) and backends that implement `run_episode(driver)`; the core `run_episode` loop is unchanged. For metrics and gates (e.g. coord contract, security), one `step_lab` call counts as one step. See the agent-driven loop implementation plan for details.

## Design choice: simulation-centric default

By default, LabTrust-Gym is **simulation-centric**: the benchmark runner owns the PettingZoo env and the step loop; LLMs and agentic coordination are **policies** (obs to actions) invoked once per step. When no LLM or MARL is used, policies are **scripted baselines** (deterministic reference policies for comparison and reproducibility; they are not state of the art — see [State of the art status and limits](../reference/state_of_the_art_and_limits.md)). This keeps a single step boundary, reproducibility, multi-agent semantics, and a single place for security and audit. With the default (no `--agent-driven`), the runner is the only component that calls `env.step`; policies only receive observations and return actions.

## Summary

| Component | Role | Uses PZ env? |
|-----------|------|--------------|
| **LabTrustParallelEnv (PettingZoo)** | Multi-agent simulation: `reset`, `step`, `agents`, observations, timing. | The env itself; used only by the benchmark runner. |
| **LLM agent (per-agent)** | Maps one agent's observation to an action (with shield). | Yes: runner gives it PZ observations, takes the returned action, passes it to `env.step`. |
| **LLM coordination methods** | Produce a joint action proposal from full obs/infos (e.g. `llm_central_planner`, `llm_repair_over_kernel_whca`). | Yes: runner gives PZ-derived obs/infos; method returns action dict; runner calls `env.step`. |
| **Agentic coordination** | Coordination method that uses an LLM with tool_calls and tool_results (e.g. `llm_central_planner_agentic`). | Yes: same loop; tools may use state derived from the simulation, but only the runner steps the env. |
| **Security suite (agent/shield)** | Tests the LLM agent and shield on synthetic inputs (scenario_ref, llm_attacker). | No: same agent interface and observation shape; no `env.reset` or `env.step`. |
| **Security suite (coord_pack_ref)** | System-level coordination-under-attack; runs full PZ env + coordination + injectors. | Yes: same as run-benchmark coord_risk / coordination pack. |
| **Agent-driven driver** (optional) | When `--agent-driven`: backend runs `run_episode(driver)`; agent calls `step_lab` to advance env. | Yes: driver holds env and calls `env.step` only when agent calls `step_lab`. |

## PettingZoo is the simulation

The **benchmark runner** is the only component that creates and drives the PettingZoo environment. When you run a benchmark (`run-benchmark`, `quick-eval`, `run-official-pack`, or a coordination study):

1. The runner builds **LabTrustParallelEnv** (in `src/labtrust_gym/envs/pz_parallel.py`), which wraps the core engine with the PettingZoo Parallel API. The env supports **render()** (ansi/human), **reset(options)** with `timing_mode`/`dt_s`, batch observation building when the engine exposes `get_agent_zones`/`get_agent_roles`, and **step_batch** when the engine supports it. See [PettingZoo API](../agents/pettingzoo_api.md) for the full contract and "How the simulation works."
2. Each step: the runner gets observations from the env, passes them to whoever chooses actions (scripted agents, LLM agent, or coordination method), then calls **`env.step(actions, action_infos)`** with the chosen actions.

So: **PettingZoo is the single simulation backend for benchmarks.** Baselines and coordination methods never call the env; they only receive observations and infos and return action dicts. See [Coordination and env data flow](../coordination/coordination_and_env.md).

## LLMs as policies in the step loop

LLMs are used in two ways, and in both cases they are **policies** that consume observations and produce actions. The LLM code does not create or step the env.

### Per-agent LLM

When you run a benchmark with LLM agents (e.g. `--llm-agents ops_0` or `--use-llm-safe-v1-ops`):

- The runner builds **LLMAgentWithShield** and puts it in `scripted_agents_map`.
- Each step, for each LLM agent, the runner calls **`agent.act(obs[agent_id])`** where `obs` comes from the previous `env.step` (or `env.reset`).
- The agent returns `(action_index, action_info)`; the runner converts that to the action dict and, after optional risk injector mutation, calls **`env.step(actions, action_infos)`**.

So the **observations** that the LLM sees are produced by the PZ env. The LLM never talks to the env directly.

### LLM-based coordination

Coordination methods such as `llm_central_planner`, `llm_auction_bidder`, or `llm_repair_over_kernel_whca` use an LLM backend to produce a **proposal** (per-agent actions). Each step:

- The runner calls **`coord_method.propose_actions(obs_for_step, infos, step_t)`** where `obs_for_step` and `infos` come from the env.
- The coordination method returns an action dict; the runner converts it to `(actions, action_infos)` and calls **`env.step(actions, action_infos)`**.

Again: observations come from the env; only the runner steps the env.

## Agentic coordination

**Agentic** here means a coordination method that runs an **LLM in a tool-call loop**: the backend may return `tool_calls`; the method executes the tools (e.g. query queue state) and calls the backend again with `tool_results` until a final proposal or a round limit.

- Example: **llm_central_planner_agentic** (`src/labtrust_gym/baselines/coordination/methods/llm_central_planner_agentic.py`). The backend (e.g. `OpenAIAgenticProposalBackend`) uses Chat Completions with tools; tools are implemented in `coord_agentic_tools.py` and can reflect simulation state (e.g. queue lengths).
- The **relationship to PettingZoo** is unchanged: the runner still owns the env. Each step it passes **observations and infos** (from the env) into the coordination method. The agentic loop runs inside the method; when the method returns an action dict, the runner calls **`env.step(actions, action_infos)`**. Tools may read state that ultimately comes from the simulation (e.g. via the blackboard or harness), but the env is still stepped only by the runner.

So: **agentic systems are coordination policies** that use an LLM with tools; they are not a separate "agentic framework" that replaces PettingZoo.

## Security suite: when the PZ env is not used

The **security attack suite** (`run-security-suite`) has two kinds of entries:

1. **Agent/shield (no PZ env)** — `scenario_ref`, `test_ref`, `llm_attacker`:
   - The suite builds **LLMAgentWithShield** and feeds it **synthetic observations** (or runs allowlisted pytest). There is no `env.reset()` or `env.step()`.
   - The agent and observation shape are the same as in benchmarks (so the same code path is tested), but the suite does not run the simulator. PettingZoo/gymnasium are required at import time only because the agent and obs shape are defined for the PZ env; see [Security attack suite](../risk-and-security/security_attack_suite.md) and [Security flows and entry points](../risk-and-security/security_flows_and_entry_points.md).

2. **System-level (PZ env required)** — `coord_pack_ref`:
   - The suite runs the full loop: build PZ env, run coordination pack (coordination method + risk injectors), evaluate gate. Same as `run-coordination-security-pack` or `run-benchmark … coord_risk`.

So: **the only way the security suite uses the PZ env is for coord_pack_ref.** All other attack types are agent/shield regression without the simulator.

## Data flow (benchmark with LLM or agentic coordination)

```
env (LabTrustParallelEnv)
    → obs, infos
    → [optional: risk_injector.mutate_obs(obs)]
    → coord_method.propose_actions(obs, infos, t)  [or scripted_agents_map / LLM agent per agent]
    → action dict
    → [optional: risk_injector.mutate_actions(actions_dict)]
    → runner converts to (actions, action_infos)
    → env.step(actions, action_infos)
```

Coordination methods (including agentic ones) never call the env; they only receive obs/infos and return an action dict. The runner is the only component that calls `env.step`.

When the number of agents exceeds **coord_propose_actions_max_agents** (default 50), simulation-centric does **not** call `propose_actions`; it collects one submission per agent and calls **`combine_submissions(submissions, obs, infos, t)`** to obtain the joint action. For **scale-capable** methods (those with scale_capable: true in policy, see [design_choices §6.3](design_choices.md)), the runner populates scripted_agents_map with one LLMAgentWithShield per agent when N > N_max so the combine path uses real per-agent policies. So at scale, only the combine path is used. See [Coordination and env](../coordination/coordination_and_env.md) and `policy/coordination/coordination_submission_shapes.v0.1.yaml` for submission shapes per method (action, bid, vote).

## Comparison with agent-centric frameworks

In frameworks like [LangChain](https://docs.langchain.com/oss/python/langchain/overview), the **agent** drives the loop: the LLM chooses an action, takes that action, sees an observation, and repeats until done. The environment (or tools) is what the agent calls.

**Default (simulation-centric):** The **simulator** drives the loop; the LLM is a policy inside that loop. The runner steps the env at a fixed rate and invokes the policy once per step. For multi-agent simulation benchmarks and security evaluation, this is the default and recommended approach.

**Optional (agent-centric):** Use `run-benchmark --agent-driven --coord-method <method>`. The LLM then drives the loop by calling a `step_lab(proposal)` tool; the driver steps the env and returns observations. Same env and safety; only the orchestration (who calls `env.step`) changes. Implemented in `agent_driven_driver.py` and backends such as `OpenAIAgentDrivenBackend` and `DeterministicAgentDrivenBackend`.

**Using LangChain under the hood:** You can use LangChain (or similar) for model I/O, prompt building, tool definitions, and parsing. With simulation-centric mode the runner steps the env and calls your policy; with agent-driven mode your backend can use LangChain inside `run_episode(driver)`.

## See also

- [Episode / simulation viewer](../reference/episode_viewer.md) — How to inspect and visualize runs (lab pipeline, step x agent grid, zone-centric view).
- [Coordination and env data flow](../coordination/coordination_and_env.md) — Per-step flow and action contract.
- [Security flows and entry points](../risk-and-security/security_flows_and_entry_points.md) — Attack suite vs coord_risk; when PZ is used.
- [System overview](system_overview.md) — Layering and where the env comes from.
- [PettingZoo API](../agents/pettingzoo_api.md) — Observation spec, action space, usage.
- [LLM baselines](../agents/llm_baselines.md) — LLM agent and backends.
- [Live LLM benchmark mode](../agents/llm_live.md) — Pipeline modes and where the LLM sits in the benchmark.
- [LangChain overview](https://docs.langchain.com/oss/python/langchain/overview) — Agent-centric pattern (agent drives the loop); contrast with LabTrust-Gym’s simulation-centric design above.
