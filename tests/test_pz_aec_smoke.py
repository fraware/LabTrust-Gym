"""
Smoke and determinism tests for PettingZoo AEC wrapper.

Requires: pip install -e ".[env]"
- Instantiate AEC env (via labtrust_aec_env), reset(seed=123), run 50 agent-steps
  with sequential observe/step, no crash.
- Determinism: same seed + same action sequence -> identical (obs hash, rewards).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.envs.pz_aec import (
    ACTION_NOOP,
    ACTION_TICK,
    labtrust_aec_env,
)


def _hash_obs(obs: Any) -> str:
    """Stable hash of observation for determinism tests."""

    def _enc(o: Any) -> Any:
        if hasattr(o, "tolist"):
            return o.tolist()
        if isinstance(o, dict):
            return {k: _enc(v) for k, v in sorted(o.items())}
        return o

    return hashlib.sha256(json.dumps(_enc(obs), sort_keys=True).encode()).hexdigest()


def test_pz_aec_instantiate_reset_step_50() -> None:
    """AEC env, reset(seed=123), 50 agent-steps sequential step, no crash."""
    env = labtrust_aec_env(num_runners=2)
    env.reset(seed=123)
    step_count = 0
    max_steps = 50
    while env.agents and step_count < max_steps:
        assert env.agent_selection is not None
        obs, reward, term, trunc, info = env.last()
        assert obs is not None
        action = ACTION_NOOP if step_count % 2 == 0 else ACTION_TICK
        env.step(action)
        step_count += 1
    env.close()
    assert step_count == max_steps


def test_pz_aec_determinism() -> None:
    """Same seed + same action sequence -> identical (obs hash, reward) per step."""

    def run_trajectory(seed: int, max_steps: int) -> list:
        env = labtrust_aec_env(num_runners=2)
        env.reset(seed=seed)
        out = []
        step_count = 0
        while env.agents and step_count < max_steps:
            obs, reward, term, trunc, _ = env.last()
            out.append((_hash_obs(obs), reward, term, trunc))
            action = ACTION_NOOP if step_count % 2 == 0 else ACTION_TICK
            env.step(action)
            step_count += 1
        env.close()
        return out

    traj1 = run_trajectory(seed=42, max_steps=20)
    traj2 = run_trajectory(seed=42, max_steps=20)
    assert len(traj1) == 20 and len(traj2) == 20
    for i in range(20):
        assert traj1[i][0] == traj2[i][0], f"step {i} obs hash differs"
        assert traj1[i][1] == traj2[i][1], f"step {i} reward differs"
        assert traj1[i][2] == traj2[i][2], f"step {i} term differs"
        assert traj1[i][3] == traj2[i][3], f"step {i} trunc differs"


def test_pz_aec_agent_selection_and_observe() -> None:
    """AEC env exposes agent_selection and observe/last."""
    env = labtrust_aec_env(num_runners=1)
    env.reset(seed=0)
    assert hasattr(env, "agent_selection")
    agent = env.agent_selection
    assert agent is not None
    obs, reward, term, trunc, info = env.last()
    assert obs is not None
    # Obs can include extra keys for LLM context; check space keys are present.
    space = env.observation_space(agent)
    if hasattr(space, "spaces"):
        for key in space.spaces:
            assert key in obs, f"observation missing space key {key!r}"
    env.step(ACTION_NOOP)
    env.close()
