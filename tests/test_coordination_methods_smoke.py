"""
Smoke tests for coordination methods: instantiate each (except marl_ppo if deps missing),
run 50 steps on tiny scale, ensure valid action dict for all active agents.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    action_dict_to_index_and_info,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.registry import make_coordination_method
from labtrust_gym.benchmarks.tasks import get_task


def _tiny_scale_policy() -> dict:
    """Minimal policy with zone_layout for coordination methods."""
    return {
        "zone_layout": {
            "zones": [
                {
                    "zone_id": "Z_A",
                    "name": "A",
                    "kind": "STAGING",
                    "temp_band": "AMBIENT_20_25",
                },
                {
                    "zone_id": "Z_B",
                    "name": "B",
                    "kind": "STAGING",
                    "temp_band": "AMBIENT_20_25",
                },
            ],
            "graph_edges": [{"from": "Z_A", "to": "Z_B", "travel_s": 10}],
            "device_placement": [
                {"device_id": "DEV_1", "zone_id": "Z_B"},
            ],
        },
    }


def _fake_obs(agent_ids: list[str], t: int) -> dict:
    """Minimal obs dict per agent for one step."""
    out = {}
    for i, aid in enumerate(agent_ids):
        out[aid] = {
            "my_zone_idx": 1 + (i % 2),
            "zone_id": "Z_B" if i % 2 else "Z_A",
            "queue_by_device": [
                {"device_id": "DEV_1", "queue_len": 0, "queue_head": None}
            ],
            "queue_has_head": [0],
            "log_frozen": 0,
            "door_restricted_open": 0,
            "restricted_zone_frozen": 0,
        }
    return out


def _run_50_steps(method: CoordinationMethod, policy: dict, scale_config: dict) -> None:
    """Run 50 steps with fake obs; assert valid action dict per agent."""
    method.reset(seed=42, policy=policy, scale_config=scale_config)
    agent_ids = ["worker_0", "worker_1"]
    infos: dict = {}
    for t in range(50):
        obs = _fake_obs(agent_ids, t)
        actions_dict = method.propose_actions(obs, infos, t)
        assert isinstance(actions_dict, dict)
        for aid in agent_ids:
            assert aid in actions_dict
            ad = actions_dict[aid]
            assert "action_index" in ad
            idx = ad["action_index"]
            assert isinstance(idx, int)
            assert 0 <= idx <= 5
            action_index, action_info = action_dict_to_index_and_info(ad)
            assert 0 <= action_index <= 5


@pytest.mark.parametrize(
    "method_id",
    [
        "centralized_planner",
        "hierarchical_hub_rr",
        "market_auction",
        "gossip_consensus",
        "swarm_reactive",
    ],
)
def test_coordination_method_smoke_50_steps(method_id: str) -> None:
    """Each non-LLM, non-MARL method runs 50 steps and returns valid actions."""
    policy = _tiny_scale_policy()
    scale_config = {"num_agents_total": 2, "num_sites": 1}
    method = make_coordination_method(
        method_id, policy, repo_root=None, scale_config=scale_config
    )
    assert isinstance(method, CoordinationMethod)
    _run_50_steps(method, policy, scale_config)


def test_centralized_planner_compute_budget() -> None:
    """Centralized planner with compute_budget limits assignments."""
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )

    policy = _tiny_scale_policy()
    scale_config = {"num_agents_total": 3, "num_sites": 1}
    method = CentralizedPlanner(compute_budget=1)
    method.reset(42, policy, scale_config)
    agents = ["worker_0", "worker_1", "worker_2"]
    obs = _fake_obs(agents, 0)
    actions_dict = method.propose_actions(obs, {}, 0)
    assert len(actions_dict) == 3
    non_noop = sum(
        1 for a in actions_dict.values() if a.get("action_index") != ACTION_NOOP
    )
    assert non_noop <= 1


def test_marl_ppo_stub_skip_if_no_deps() -> None:
    """marl_ppo is skipped (or raises) when SB3 not installed."""
    try:
        import stable_baselines3  # noqa: F401
        import gymnasium  # noqa: F401

        pytest.skip("SB3 installed; test only runs when marl extra missing")
    except ImportError:
        pass
    with pytest.raises((ImportError, NotImplementedError)):
        make_coordination_method(
            "marl_ppo",
            {},
            repo_root=None,
            scale_config={"num_agents_total": 2},
        )


def test_llm_constrained_requires_llm_agent() -> None:
    """llm_constrained raises if llm_agent not provided."""
    with pytest.raises(ValueError, match="llm_constrained requires llm_agent"):
        make_coordination_method(
            "llm_constrained",
            _tiny_scale_policy(),
            repo_root=None,
            scale_config={},
        )


def test_unknown_method_raises() -> None:
    """Unknown method_id raises ValueError."""
    with pytest.raises(ValueError, match="Unknown coordination method_id"):
        make_coordination_method("nonexistent", {}, repo_root=None)
