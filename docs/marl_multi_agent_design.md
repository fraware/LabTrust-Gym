# MARL multi-agent design

This document describes the multi-agent MARL design in LabTrust-Gym: shared PPO policy with agent_id in observation, and how it is used in training and the `marl_ppo` coordination method.

## Implemented: shared policy with agent_id in obs

- **Training:** `labtrust train-ppo` trains a single **shared** policy. The observation includes a **one-hot agent_id** (default `num_agents=5`: ops_0, runner_0, runner_1, qc_0, supervisor_0). During training only **ops_0** is controlled (agent_index 0); other agents are scripted. The policy thus sees `flat_obs + one_hot(0)` and learns to act for the scheduler; the same network can later be used for other agents by feeding `flat_obs + one_hot(i)`.
- **Coordination method `marl_ppo`:** When the `[marl]` extra is installed and a **trained model path** is provided (e.g. from `labtrust train-ppo --out runs/ppo`), `MarlPPOCoordination` loads the model and `train_config.json` (n_d, n_status, obs_history_len, include_agent_id, num_agents). In `propose_actions(obs, infos, t)`, for each agent it flattens that agent's observation, optionally stacks history, appends `one_hot(agent_index)`, and calls the shared policy. So all agents are driven by the same policy with agent identity in the observation.
- **Eval-agent (PPOAgent):** When loading a model trained with `include_agent_id=True`, the eval agent appends `one_hot(0)` to the observation so the input shape matches training.
- **Config:** `train_config` (or CLI) supports `include_agent_id` (default True) and `num_agents` (default 5). Set `include_agent_id: false` for legacy single-agent obs (no one-hot).

## Observation layout

- **Flat obs:** `get_flat_obs_dim(n_d, n_status)` gives the per-step dimension; with `obs_history_len` the base vector is `flat_dim * obs_history_len`.
- **With agent_id:** Total obs = base vector + one-hot of length `num_agents`. Implemented in `sb3_wrapper` (`_one_hot_agent`, `get_obs_dim_with_agent_id`) and used in the Gymnasium wrapper, PPOAgent, and marl_ppo coordination.

## MAPPO/CTDE (future implementation)

**Goal:** Offer MAPPO or a CTDE-style algorithm (centralized critic, decentralized execution) as an alternative to the current shared PPO with agent_id in obs, for stronger multi-agent credit assignment.

**Options:**

1. **sb3-contrib MAPPO:** If the API fits our env, use [sb3-contrib MAPPO](https://github.com/Stable-Baselines-Team/stable-baselines3-contrib). It expects a vectorized multi-agent env (e.g. one that returns obs/rew/done for all agents). Our `LabTrustParallelEnv` is PettingZoo Parallel; we would need an adapter that presents a single-step multi-agent batch (all agents’ obs, actions, rewards) or use sb3-contrib’s multi-agent wrappers if they support our observation/action layout.
2. **Minimal custom CTDE:** A small wrapper that keeps decentralized policies (one per agent or shared policy with agent_id) but adds a **centralized value**: value input = global state or concatenated observations from all agents. Training: policy gradient with value from the centralized critic; execution: each agent uses only its local obs + agent_id (no global state). This avoids depending on sb3-contrib and keeps save/load compatible with current `train_config` (obs shape, num_agents, include_agent_id).

**Alignment with current code:**

- **Observation:** `sb3_wrapper` already provides flat_obs + one_hot(agent_id) per agent. For a centralized critic, global state can be the concatenation of all agents’ flat_obs (and optionally env-level features from `infos` if available).
- **Action space:** Same as today: discrete action per agent from `env.action_space(agent_id)`; multi-discrete or single discrete depending on `pz_parallel` setup.
- **train_config:** Should continue to store `n_d`, `n_status`, `obs_history_len`, `include_agent_id`, `num_agents` so that eval and `marl_ppo` coordination can load the policy. Add an optional `algorithm: "mappo"` (or `"ctde"`) to select the training path; when absent, current shared PPO is used.

**Implementation steps (when implementing):**

1. Decide sb3-contrib MAPPO vs custom CTDE based on env API fit and dependency tolerance.
2. If sb3-contrib: add adapter from PettingZoo Parallel to the multi-agent format MAPPO expects; add `algorithm: mappo` to train_config and a CLI/entry that calls MAPPO training; ensure saved policy is loadable by existing eval-agent or marl_ppo (may require a thin wrapper to match our obs/action interface).
3. If custom CTDE: implement a training loop that (a) collects transitions with current env and agent_id in obs, (b) computes value from centralized state (e.g. concat of all obs), (c) updates policy with PPO-style loss using that value; save policy and train_config in the same shape as current PPO so `MarlPPOCoordination` and PPOAgent can load it.
4. Document in [MARL baselines](marl_baselines.md) the new option and any extra dependencies.

**Current status:** Design only; no MAPPO/CTDE implementation yet. Shared PPO with agent_id remains the supported MARL path.

## Other optional future work

- **Train multiple agents:** Extend the training loop so more than one agent is learned (e.g. ops_0 and runners) with agent_id in obs; the current setup trains only ops_0 with agent_id so the same policy can be used at inference for all agents.

## References

- `src/labtrust_gym/baselines/marl/` — PPO training, sb3_wrapper (include_agent_id, num_agents), ppo_agent for eval-agent.
- `src/labtrust_gym/baselines/coordination/methods/marl_ppo.py` — MarlPPOCoordination (shared policy + agent_id).
- `src/labtrust_gym/envs/pz_parallel.py` — Observation and action space; agent set.
- `policy/coordination/coordination_methods.v0.1.yaml` — `marl_ppo` entry.
- [MARL baselines](marl_baselines.md) — CLI, train_config, multi-agent section.
