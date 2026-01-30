"""
Smoke and determinism tests for PettingZoo Parallel wrapper.

Requires: pip install -e ".[env]"
- Instantiate env, reset(seed=123), run 50 steps with (deterministic) random legal actions, no crash.
- Determinism: same seed + same actions -> identical (obs hash, rewards, terminations).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.envs.pz_parallel import (
    LabTrustParallelEnv,
    _hash_obs,
    ACTION_NOOP,
    ACTION_TICK,
)


def test_pz_parallel_instantiate_reset_step_50() -> None:
    """Instantiate env, reset(seed=123), run 50 steps with random legal actions, no crash."""
    env = LabTrustParallelEnv(num_runners=2)
    obs, infos = env.reset(seed=123)
    assert obs is not None
    assert len(obs) == len(env.agents)
    for _ in range(50):
        actions = {a: ACTION_NOOP for a in env.agents}
        if _ % 2 == 1:
            actions = {a: ACTION_TICK for a in env.agents}
        obs, rewards, terminations, truncations, infos = env.step(actions)
        assert obs is not None
        assert len(rewards) == len(env.agents)
        assert len(terminations) == len(env.agents)
        assert len(truncations) == len(env.agents)
    env.close()


def test_pz_parallel_determinism() -> None:
    """Same seed + same actions yields identical sequence of (obs hash, rewards, terminations)."""
    def run_trajectory(seed: int, steps: int) -> list:
        env = LabTrustParallelEnv(num_runners=2)
        env.reset(seed=seed)
        out = []
        for step in range(steps):
            actions = {
                a: (ACTION_NOOP if step % 2 == 0 else ACTION_TICK)
                for a in env.agents
            }
            obs, rewards, terminations, truncations, _ = env.step(actions)
            out.append((
                _hash_obs(obs),
                tuple(sorted(rewards.items())),
                tuple(sorted(terminations.items())),
            ))
        env.close()
        return out

    traj1 = run_trajectory(seed=42, steps=10)
    traj2 = run_trajectory(seed=42, steps=10)
    assert len(traj1) == 10 and len(traj2) == 10
    for i in range(10):
        assert traj1[i][0] == traj2[i][0], f"step {i} obs hash differs"
        assert traj1[i][1] == traj2[i][1], f"step {i} rewards differ"
        assert traj1[i][2] == traj2[i][2], f"step {i} terminations differ"


def test_pz_parallel_observation_action_spaces() -> None:
    """Observation and action spaces are defined for all agents."""
    env = LabTrustParallelEnv(num_runners=1)
    env.reset(seed=0)
    for agent in env.agents:
        ob_space = env.observation_space(agent)
        ac_space = env.action_space(agent)
        assert ob_space is not None
        assert ac_space is not None
        obs, _ = env.reset(seed=0)
        ob = obs[agent]
        assert ob_space.contains(ob), f"obs for {agent} not in space"
        ac = int(ac_space.sample())
        assert ac_space.contains(ac)
    env.close()
