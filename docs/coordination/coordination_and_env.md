# Coordination and environment

The benchmark runner owns the env (LabTrustParallelEnv). Each step:

1. Observations from env.
2. Optional: `risk_injector.mutate_obs(obs)`.
3. Coordination method produces action dicts via `propose_actions(obs_for_step, infos, t)` or `step(context)`.
4. Optional: `risk_injector.mutate_actions(actions_dict)`.
5. Runner converts action_dict to `(actions, action_infos)` and calls `env.step(actions, action_infos)`.

Coordination methods never call the env; they only receive obs and infos and return action dicts. In **simulation-centric** mode the runner is the only component that calls `env.step`. When the number of agents is **at or below** `coord_propose_actions_max_agents` (default 50), the runner uses `propose_actions(obs, infos, t)` or `step(context)` (kernel-composed methods). When the number of agents is **above** that threshold, the runner does **not** call `propose_actions`; it collects one **submission** per agent (from `scripted_agents_map` or NOOP) and calls `coord_method.combine_submissions(submissions, obs, infos, t)` to obtain the joint action dict. So at scale, only the combine path is used. Scale-capable methods (those with scale_capable: true in coordination_methods.v0.1.yaml) get scripted_agents_map populated with one LLM agent per agent when N > N_max; see [design_choices §6.1 and §6.3](../architecture/design_choices.md). In **agent-centric** mode (`run-benchmark --agent-driven`), a driver holds the env and runs the same flow (mutate_obs, proposal from agent, mutate_actions, env.step) when the agent calls the step_lab tool; the driver is the only component that calls `env.step`. Coordination can be scripted, LLM-based (e.g. `llm_central_planner`), or agentic (e.g. `llm_central_planner_agentic`, with a tool-call loop). The action dicts produced and (after mutate_actions) passed to `env.step` conform to the [Action contract](../contracts/frozen_contracts.md#action-contract-v01) (see `envs/action_contract.py`). For how PettingZoo, LLMs, and the two orchestration modes fit together, see [Simulation, LLMs, and agentic systems](../architecture/simulation_llm_agentic.md).
