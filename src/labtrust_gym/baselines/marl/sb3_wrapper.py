"""
Gymnasium wrapper for LabTrustParallelEnv for PPO (stable-baselines3).

Supports single-agent (ops_0 only) and multi-agent: when include_agent_id is True,
observation is flat_obs + one_hot(agent_id) so a shared policy can condition on agent.
Other agents use scripted policies during single-agent training.
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    import gymnasium
    from gymnasium import spaces
except ImportError:
    gymnasium = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]


def get_flat_obs_dim(n_d: int = 6, n_status: int = 8) -> int:
    """Observation dimension for a single step (before history stacking)."""
    return 1 + 1 + 1 + 1 + n_d + n_d + n_status + n_d + 1 + 1 + 1


def get_obs_dim_with_agent_id(
    n_d: int = 6,
    n_status: int = 8,
    obs_history_len: int = 1,
    num_agents: int = 1,
    include_agent_id: bool = False,
) -> int:
    """Total observation dimension: flat_dim * obs_history_len + (num_agents if include_agent_id else 0)."""
    single = get_flat_obs_dim(n_d, n_status)
    total = single * max(1, obs_history_len)
    if include_agent_id and num_agents > 0:
        total += num_agents
    return total


def _one_hot_agent(agent_index: int, num_agents: int) -> np.ndarray:
    """One-hot vector of length num_agents; index clamped to [0, num_agents-1]."""
    x = np.zeros(num_agents, dtype=np.float32)
    idx = max(0, min(agent_index, num_agents - 1))
    x[idx] = 1.0
    return x


def _flatten_obs(obs: dict[str, Any], n_d: int = 6, n_status: int = 8) -> Any:
    """Flatten ops_0 observation dict to a single float32 vector."""
    parts: list[Any] = []
    parts.append(np.array([float(obs.get("my_zone_idx", 0))], dtype=np.float32))
    parts.append(np.array([float(obs.get("door_restricted_open", 0))], dtype=np.float32))
    dur = obs.get("door_restricted_duration_s")
    if dur is not None and hasattr(dur, "flatten"):
        parts.append(np.asarray(dur, dtype=np.float32).flatten())
    else:
        parts.append(np.array([0.0], dtype=np.float32))
    parts.append(np.array([float(obs.get("restricted_zone_frozen", 0))], dtype=np.float32))
    ql = obs.get("queue_lengths")
    if ql is not None:
        parts.append(np.asarray(ql, dtype=np.float32).flatten()[:n_d])
    else:
        parts.append(np.zeros(n_d, dtype=np.float32))
    qh = obs.get("queue_has_head")
    if qh is not None:
        parts.append(np.asarray(qh, dtype=np.float32).flatten()[:n_d])
    else:
        parts.append(np.zeros(n_d, dtype=np.float32))
    sc = obs.get("specimen_status_counts")
    if sc is not None:
        parts.append(np.asarray(sc, dtype=np.float32).flatten()[:n_status])
    else:
        parts.append(np.zeros(n_status, dtype=np.float32))
    dq = obs.get("device_qc_pass")
    if dq is not None:
        parts.append(np.asarray(dq, dtype=np.float32).flatten()[:n_d])
    else:
        parts.append(np.ones(n_d, dtype=np.float32))
    parts.append(np.array([float(obs.get("log_frozen", 0))], dtype=np.float32))
    to = obs.get("token_count_override")
    if to is not None:
        parts.append(np.asarray(to, dtype=np.float32).flatten()[:1])
    else:
        parts.append(np.array([0.0], dtype=np.float32))
    tr = obs.get("token_count_restricted")
    if tr is not None:
        parts.append(np.asarray(tr, dtype=np.float32).flatten()[:1])
    else:
        parts.append(np.array([0.0], dtype=np.float32))
    return np.concatenate(parts)


if gymnasium is not None and spaces is not None:

    class LabTrustGymnasiumWrapper(gymnasium.Env):  # type: ignore[type-arg]
        """
        Gymnasium env wrapping LabTrustParallelEnv for PPO.
        When include_agent_id is True, obs = flat_obs + one_hot(agent_id) for shared multi-agent policy.
        Controlled agent: ops_0 (agent_index 0). Other agents use scripted_agents_map.
        obs_history_len: number of last steps concatenated into observation (partial observability).
        """

        def __init__(
            self,
            env: Any,
            controlled_agent: str = "ops_0",
            scripted_agents_map: dict[str, Any] | None = None,
            max_steps: int = 80,
            n_d: int = 6,
            n_status: int = 8,
            num_action_types: int = 6,
            obs_history_len: int = 1,
            reward_scale_schedule: list[tuple[float, float]] | None = None,
            include_agent_id: bool = False,
            num_agents: int = 1,
        ) -> None:
            super().__init__()
            self._env = env
            self._controlled = controlled_agent
            self._scripted = scripted_agents_map or {}
            self._max_steps = max_steps
            self._step_count = 0
            self._last_obs: dict[str, Any] = {}
            self._n_d = n_d
            self._n_status = n_status
            self._num_action_types = num_action_types
            self._obs_history_len = max(1, int(obs_history_len))
            self._reward_scale_schedule = reward_scale_schedule or []
            self._include_agent_id = bool(include_agent_id)
            self._num_agents = max(1, int(num_agents))
            self._agent_index = 0
            obs_dim = get_obs_dim_with_agent_id(
                n_d=n_d,
                n_status=n_status,
                obs_history_len=self._obs_history_len,
                num_agents=self._num_agents,
                include_agent_id=self._include_agent_id,
            )
            self._obs_history: list[Any] = []
            self.observation_space = spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=(obs_dim,),
                dtype=np.float32,
            )
            self.action_space = spaces.Discrete(num_action_types)

        def _build_obs_vector(self, flat: np.ndarray) -> np.ndarray:
            """Stack history and optionally append one_hot(agent_id)."""
            stacked = np.concatenate(self._obs_history, axis=0)
            if self._include_agent_id:
                stacked = np.concatenate(
                    [stacked, _one_hot_agent(self._agent_index, self._num_agents)],
                    axis=0,
                )
            return stacked.astype(np.float32)

        def reset(
            self,
            seed: int | None = None,
            options: dict[str, Any] | None = None,
        ) -> tuple[Any, dict[str, Any]]:
            self._step_count = 0
            if seed is not None:
                self._env.seed(seed)
            obs_dict, _ = self._env.reset(seed=seed, options=options)
            self._last_obs = obs_dict
            flat = _flatten_obs(
                obs_dict.get(self._controlled, {}),
                n_d=self._n_d,
                n_status=self._n_status,
            )
            self._obs_history = [flat] * self._obs_history_len
            return self._build_obs_vector(flat), {}

        def step(self, action: int) -> tuple[Any, float, bool, bool, dict[str, Any]]:
            obs_dict = self._last_obs
            actions: dict[str, Any] = {}
            action_infos: dict[str, dict[str, Any]] = {}
            for agent in self._env.agents:
                if agent == self._controlled:
                    actions[agent] = int(action)
                    if action == 2:
                        action_infos[agent] = {
                            "work_id": "ppo_work",
                            "device_id": self._env._device_ids[0]
                            if getattr(self._env, "_device_ids", None)
                            else "DEV_CHEM_A_01",
                            "priority": "ROUTINE",
                        }
                elif agent in self._scripted:
                    a_idx, a_info = self._scripted[agent].act(obs_dict.get(agent, {}), agent)
                    actions[agent] = a_idx
                    if a_info and a_idx not in (0, 1):
                        action_infos[agent] = a_info
                else:
                    actions[agent] = 0
            obs_dict, rewards, term, trunc, infos = self._env.step(actions, action_infos=action_infos)
            self._last_obs = obs_dict
            self._step_count += 1
            flat = _flatten_obs(
                obs_dict.get(self._controlled, {}),
                n_d=self._n_d,
                n_status=self._n_status,
            )
            self._obs_history = (self._obs_history + [flat])[-self._obs_history_len:]
            stacked = self._build_obs_vector(flat)
            reward = float(rewards.get(self._controlled, 0.0))
            scale = _reward_scale_for_step(
                self._step_count - 1, self._max_steps, self._reward_scale_schedule
            )
            reward = reward * scale
            truncated = self._step_count >= self._max_steps
            terminated = False
            info = dict(infos.get(self._controlled, {}))
            return stacked, reward, terminated, truncated, info

        def close(self) -> None:
            self._env.close()

else:
    LabTrustGymnasiumWrapper = None  # type: ignore[misc]


def _reward_scale_for_step(step: int, max_steps: int, schedule: list[tuple[float, float]]) -> float:
    """Return scale factor for current step from schedule [(step_frac, scale), ...]."""
    if not schedule or max_steps <= 0:
        return 1.0
    frac = step / max_steps
    scale = schedule[0][1]
    for step_frac, s in schedule:
        if step_frac <= frac:
            scale = s
    return scale


def make_task_env(
    task_name: str = "throughput_sla",
    max_steps: int = 80,
    reward_config: dict[str, Any] | None = None,
    obs_history_len: int = 1,
    reward_scale_schedule: list[tuple[float, float]] | None = None,
    include_agent_id: bool = False,
    num_agents: int = 1,
) -> tuple[Any, Any]:
    """
    Create LabTrustParallelEnv for task and wrap for SB3.
    Returns (gym_env, raw_parallel_env).
    obs_history_len: stack last N observations (partial observability); default 1.
    reward_scale_schedule: curriculum [(step_frac, scale), ...]; e.g. [(0, 0.5), (0.5, 1.0)].
    include_agent_id: if True, obs = flat_obs + one_hot(agent_id) for shared multi-agent policy.
    num_agents: size of one-hot (e.g. 5 for ops_0, runner_0, runner_1, qc_0, supervisor_0).
    Caller must call gym_env.reset(seed=..., options={"initial_state": task.get_initial_state(seed)}).
    """
    from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.envs.pz_parallel import (
        DEFAULT_DEVICE_IDS,
        DEFAULT_ZONE_IDS,
        LabTrustParallelEnv,
    )

    task = get_task(task_name)
    reward_config = reward_config or task.reward_config
    max_steps = getattr(task, "max_steps", None) or max_steps
    raw = LabTrustParallelEnv(
        num_runners=2,
        num_adversaries=0,
        dt_s=10,
        reward_config=reward_config,
    )
    scripted = {
        "runner_0": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS,
            device_ids=DEFAULT_DEVICE_IDS,
        ),
        "runner_1": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS,
            device_ids=DEFAULT_DEVICE_IDS,
        ),
    }
    gym_env = LabTrustGymnasiumWrapper(
        raw,
        controlled_agent="ops_0",
        scripted_agents_map=scripted,
        max_steps=max_steps,
        obs_history_len=obs_history_len,
        reward_scale_schedule=reward_scale_schedule,
        include_agent_id=include_agent_id,
        num_agents=num_agents,
    )
    return gym_env, raw
