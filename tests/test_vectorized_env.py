"""
Minimal tests for LabTrustVectorEnv (N envs in one process).

Requires: pip install -e ".[env]"
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.envs.pz_parallel import ACTION_NOOP, ACTION_TICK
from labtrust_gym.envs.vectorized import AsyncLabTrustVectorEnv, LabTrustVectorEnv


def test_vectorized_env_instantiate_reset_step() -> None:
    """Instantiate LabTrustVectorEnv(2), reset, step once; check list lengths and agents."""
    env = LabTrustVectorEnv(2, num_runners=2, base_seed=42)
    assert env.num_envs == 2
    obs_list, infos_list = env.reset(seed=100)
    assert len(obs_list) == 2
    assert len(infos_list) == 2
    agents = env.agents
    assert len(agents) > 0
    for i, obs in enumerate(obs_list):
        assert set(obs.keys()) == set(agents)
    actions_list = [
        {a: ACTION_NOOP for a in agents},
        {a: ACTION_TICK for a in agents},
    ]
    obs_list, rewards_list, terms_list, truncs_list, infos_list = env.step(actions_list)
    assert len(obs_list) == 2
    assert len(rewards_list) == 2
    assert len(terms_list) == 2
    assert len(truncs_list) == 2
    assert len(infos_list) == 2
    for i in range(2):
        assert set(obs_list[i].keys()) == set(agents)
        assert set(rewards_list[i].keys()) == set(agents)
    env.close()


def test_async_vectorized_env_instantiate_reset_step() -> None:
    """Instantiate AsyncLabTrustVectorEnv(2), reset, step once; same API as sync, parallel execution."""
    async_env = AsyncLabTrustVectorEnv(2, num_runners=2, base_seed=42)
    assert async_env.num_envs == 2
    obs_list, infos_list = async_env.reset(seed=100)
    assert len(obs_list) == 2
    assert len(infos_list) == 2
    agents = async_env.agents
    assert len(agents) > 0
    actions_list = [
        {a: ACTION_NOOP for a in agents},
        {a: ACTION_TICK for a in agents},
    ]
    obs_list, rewards_list, terms_list, truncs_list, infos_list = async_env.step(actions_list)
    assert len(obs_list) == 2
    assert len(rewards_list) == 2
    assert len(terms_list) == 2
    assert len(truncs_list) == 2
    assert len(infos_list) == 2
    async_env.close()


def test_labtrust_vector_env_reset_async_step_async() -> None:
    """LabTrustVectorEnv.reset_async and step_async return same shapes as sync API."""
    env = LabTrustVectorEnv(2, num_runners=2, base_seed=42)

    async def _run() -> None:
        obs_list, infos_list = await env.reset_async(seed=99)
        assert len(obs_list) == 2
        assert len(infos_list) == 2
        agents = env.agents
        assert len(agents) > 0
        for obs in obs_list:
            assert set(obs.keys()) == set(agents)
        actions_list = [
            {a: ACTION_NOOP for a in agents},
            {a: ACTION_TICK for a in agents},
        ]
        obs_list, rewards_list, terms_list, truncs_list, infos_list = await env.step_async(actions_list)
        assert len(obs_list) == 2
        assert len(rewards_list) == 2
        assert len(terms_list) == 2
        assert len(truncs_list) == 2
        assert len(infos_list) == 2

    asyncio.run(_run())
    env.close()


def test_labtrust_vector_env_async_determinism_same_seed() -> None:
    """Two async runs with the same seed yield identical rewards and terminations."""
    seed = 1777

    async def _run_one() -> tuple[list, list, list]:
        env = LabTrustVectorEnv(2, num_runners=2, base_seed=42)
        await env.reset_async(seed=seed)
        agents = env.agents
        actions_list = [
            {a: ACTION_NOOP for a in agents},
            {a: ACTION_TICK for a in agents},
        ]
        obs_list, rewards_list, terms_list, truncs_list, _ = await env.step_async(actions_list)
        env.close()
        return obs_list, rewards_list, terms_list

    async def _run_both() -> None:
        obs_a, rewards_a, terms_a = await _run_one()
        obs_b, rewards_b, terms_b = await _run_one()
        assert len(obs_a) == len(obs_b), "observation list length must match"
        for i in range(len(obs_a)):
            assert set(obs_a[i].keys()) == set(obs_b[i].keys()), f"env {i}: agent keys must match"
        assert rewards_a == rewards_b, "rewards must be identical for same seed"
        assert terms_a == terms_b, "terminations must be identical for same seed"

    asyncio.run(_run_both())
