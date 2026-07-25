"""
PettingZoo official API conformance and lifecycle tests.

Requires: pip install -e ".[env]"
- parallel_api_test against LabTrustParallelEnv
- api_test against labtrust_aec_env via space-projected Parallel wrapper
  (raw observations include LLM context keys beyond the Dict RL space)
- Space membership, agent lifecycle, termination/truncation, seeding,
  parallel/AEC equivalence for the declared observation keys
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

import numpy as np
from pettingzoo.test import api_test, parallel_api_test

from labtrust_gym.envs.action_contract import NUM_ACTION_TYPES
from labtrust_gym.envs.api_conformance import (
    ProjectObsToSpaceParallel,
    project_obs_to_space,
)
from labtrust_gym.envs.pz_aec import labtrust_aec_env
from labtrust_gym.envs.pz_parallel import (
    ACTION_NOOP,
    ACTION_TICK,
    LabTrustParallelEnv,
)


def _hash_projected(obs: dict[str, Any], space: Any) -> str:
    projected = project_obs_to_space(obs, space)

    def _enc(o: Any) -> Any:
        if hasattr(o, "tolist"):
            return o.tolist()
        if isinstance(o, dict):
            return {k: _enc(v) for k, v in sorted(o.items())}
        return o

    return hashlib.sha256(json.dumps(_enc(projected), sort_keys=True).encode()).hexdigest()


def test_parallel_official_api_test() -> None:
    """PettingZoo parallel_api_test against LabTrustParallelEnv."""
    env = LabTrustParallelEnv(num_runners=1)
    parallel_api_test(env, num_cycles=25)
    env.close()


def test_aec_official_api_test_flattened() -> None:
    """
    PettingZoo api_test against AEC with FlattenObsWrapper (Box observations).

    Raw Dict observations include LLM context keys outside the declared RL Dict
    space, and PettingZoo api_test assumes Dict spaces use an ``observation``
    sub-key (action-mask style). Flattened Box obs is the MARL-facing surface
    that official api_test validates end-to-end.
    """
    from pettingzoo.utils.conversions import parallel_to_aec

    from labtrust_gym.baselines.marl.sb3_wrapper import FlattenObsWrapper

    if FlattenObsWrapper is None:
        pytest.skip("FlattenObsWrapper requires pettingzoo and gymnasium")
    raw = LabTrustParallelEnv(num_runners=1)
    flat = FlattenObsWrapper(raw, n_d=6, n_status=8)
    env = parallel_to_aec(flat)
    api_test(env, num_cycles=25)
    env.close()


def test_aec_dict_obs_space_membership_via_projection() -> None:
    """Space-projected AEC observations pass Dict.contains (api_test precondition)."""
    if ProjectObsToSpaceParallel is None:
        pytest.skip("ProjectObsToSpaceParallel requires pettingzoo")
    from pettingzoo.utils.conversions import parallel_to_aec

    raw = LabTrustParallelEnv(num_runners=1)
    projected = ProjectObsToSpaceParallel(raw)
    env = parallel_to_aec(projected)
    env.reset(seed=0)
    step_count = 0
    while env.agents and step_count < 20:
        agent = env.agent_selection
        obs, _, term, trunc, _ = env.last()
        space = env.observation_space(agent)
        assert space.contains(obs), f"projected AEC obs for {agent} not in space"
        if term or trunc:
            env.step(None)
        else:
            env.step(ACTION_NOOP)
        step_count += 1
    env.close()


def test_observation_space_membership_projected() -> None:
    """Declared Dict space keys of each observation are in observation_space."""
    env = LabTrustParallelEnv(num_runners=2)
    obs, _ = env.reset(seed=7)
    for agent in env.agents:
        space = env.observation_space(agent)
        projected = project_obs_to_space(obs[agent], space)
        assert space.contains(projected), f"{agent} projected obs not in space"
        assert env.action_space(agent).n == NUM_ACTION_TYPES
        assert env.action_space(agent).contains(0)
        assert env.action_space(agent).contains(NUM_ACTION_TYPES - 1)
        assert not env.action_space(agent).contains(NUM_ACTION_TYPES)
    actions = {a: ACTION_NOOP for a in env.agents}
    obs2, _, _, _, _ = env.step(actions)
    for agent in env.agents:
        space = env.observation_space(agent)
        assert space.contains(project_obs_to_space(obs2[agent], space))
    env.close()


def test_action_space_discrete_0_to_5() -> None:
    """Action contract is Discrete over indices 0..5 inclusive."""
    env = LabTrustParallelEnv(num_runners=1)
    env.reset(seed=0)
    for agent in env.agents:
        space = env.action_space(agent)
        assert space.n == 6
        for a in range(6):
            assert space.contains(a)
    env.close()


def test_agent_lifecycle_possible_agents_stable() -> None:
    """possible_agents fixed; agents remain live across NOOP/TICK steps."""
    env = LabTrustParallelEnv(num_runners=2)
    obs, _ = env.reset(seed=1)
    possible = list(env.possible_agents)
    assert set(env.agents) == set(possible)
    assert set(obs.keys()) >= set(env.agents)
    for step in range(10):
        actions = {a: (ACTION_NOOP if step % 2 == 0 else ACTION_TICK) for a in env.agents}
        obs, rewards, terminations, truncations, infos = env.step(actions)
        assert list(env.possible_agents) == possible
        assert set(env.agents) == set(possible)
        assert set(rewards) == set(env.agents)
        assert set(terminations) == set(env.agents)
        assert set(truncations) == set(env.agents)
        assert set(infos) == set(env.agents)
        assert all(v is False for v in terminations.values())
        assert all(v is False for v in truncations.values())
    env.close()


def test_dead_agent_handling_no_revivals() -> None:
    """
    LabTrust default episodes do not terminate agents; if an agent were marked
    terminated, PettingZoo parallel semantics forbid revival (covered by parallel_api_test).
    """
    env = LabTrustParallelEnv(num_runners=1)
    env.reset(seed=0)
    for _ in range(5):
        obs, rewards, terminations, truncations, _ = env.step(
            {a: ACTION_NOOP for a in env.agents}
        )
        assert env.agents
        assert not any(terminations.values())
        assert not any(truncations.values())
        assert set(obs) == set(env.agents)
    env.close()


def test_seeding_reset_determinism() -> None:
    """Same seed + same actions => identical projected observation hashes; seed is stored."""

    def traj(seed: int) -> list[str]:
        env = LabTrustParallelEnv(num_runners=2)
        obs, _ = env.reset(seed=seed)
        assert env._seed_value == seed
        out = [_hash_projected(obs[a], env.observation_space(a)) for a in sorted(obs)]
        for step in range(8):
            actions = {a: (ACTION_TICK if step % 2 else ACTION_NOOP) for a in env.agents}
            obs, _, _, _, _ = env.step(actions)
            out.extend(_hash_projected(obs[a], env.observation_space(a)) for a in sorted(obs))
        env.close()
        return out

    assert traj(99) == traj(99)
    env = LabTrustParallelEnv(num_runners=1)
    env.reset(seed=123)
    assert env._seed_value == 123
    env.seed(456)
    env.reset()
    assert env._seed_value == 456
    env.close()


def test_parallel_aec_equivalence_projected() -> None:
    """
    Same seed and per-agent action stream yield matching projected obs hashes
    for Parallel vs AEC (AEC steps agents in possible_agents order each cycle).
    """
    seed = 42
    num_cycles = 5
    parallel = LabTrustParallelEnv(num_runners=1)
    obs_p, _ = parallel.reset(seed=seed)
    hashes_p: list[str] = []
    action_plan: list[dict[str, int]] = []
    for cycle in range(num_cycles):
        actions = {
            a: (ACTION_NOOP if (cycle + i) % 2 == 0 else ACTION_TICK)
            for i, a in enumerate(parallel.agents)
        }
        action_plan.append(dict(actions))
        obs_p, _, _, _, _ = parallel.step(actions)
        for a in sorted(obs_p):
            hashes_p.append(_hash_projected(obs_p[a], parallel.observation_space(a)))
    parallel.close()

    aec = labtrust_aec_env(num_runners=1)
    aec.reset(seed=seed)
    hashes_a: list[str] = []
    for cycle, actions in enumerate(action_plan):
        for agent in list(aec.possible_agents):
            assert aec.agent_selection == agent
            obs, _, _, _, _ = aec.last()
            hashes_a.append(_hash_projected(obs, aec.observation_space(agent)))
            aec.step(actions[agent])
        # After a full AEC cycle, compare last projected obs per agent from this cycle
        # (hashes_a collected pre-step; align with parallel post-step by taking post-cycle observe)
    # Re-run AEC collecting post-cycle observations to match Parallel post-step semantics
    aec.close()
    aec = labtrust_aec_env(num_runners=1)
    aec.reset(seed=seed)
    hashes_a_post: list[str] = []
    for actions in action_plan:
        for agent in list(aec.possible_agents):
            aec.step(actions[agent])
        # After full parallel-equivalent cycle, observe each agent via last()/observe
        # Agent selection is first agent of next cycle; pull obs via observe for all.
        for agent in sorted(aec.possible_agents):
            o = aec.observe(agent)
            hashes_a_post.append(_hash_projected(o, aec.observation_space(agent)))
    aec.close()

    assert hashes_p == hashes_a_post, "Parallel and AEC projected trajectories diverge"
