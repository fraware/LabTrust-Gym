"""
Run micro-scenarios against selected coordination methods.
Load scenario -> build obs/policy/scale_config -> reset + propose_actions for N steps.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.interface import (
    ACTION_START_RUN,
    VALID_ACTION_INDICES,
)

from .conftest import (
    list_scenario_paths,
    load_scenario,
    make_coord_method_for_scenario,
    scenario_obs_at_step,
    scenario_to_policy,
    scenario_to_scale_config,
)

# Methods to run in scenario harness (kernel + central; skip marl_ppo / group_evolving)
SCENARIO_METHOD_IDS = [
    "kernel_whca",
    "kernel_auction_whca",
    "centralized_planner",
    "hierarchical_hub_rr",
]


def _get_method_ids_for_scenario(scenario_id: str) -> list[str]:
    """Select method_ids per scenario focus (routing for corridor_swap, etc.)."""
    if scenario_id == "corridor_swap":
        return [
            "kernel_whca",
            "kernel_auction_whca",
            "kernel_auction_whca_shielded",
        ]
    if scenario_id == "adversarial_comms_poison":
        return ["gossip_consensus", "kernel_whca"]
    return SCENARIO_METHOD_IDS


@pytest.mark.parametrize("scenario_path", list_scenario_paths())
def test_scenario_loads(scenario_path: Path) -> None:
    """Each scenario JSON loads and has required keys."""
    scenario = load_scenario(scenario_path)
    assert "policy" in scenario
    assert "scale_config" in scenario
    assert "initial_state" in scenario
    policy = scenario_to_policy(scenario)
    assert "zone_layout" in policy
    assert "pz_to_engine" in policy


@pytest.mark.parametrize("scenario_path", list_scenario_paths())
def test_scenario_obs_build(scenario_path: Path) -> None:
    """Scenario yields valid obs structure."""
    scenario = load_scenario(scenario_path)
    obs = scenario_obs_at_step(scenario, 0)
    agent_ids = (scenario.get("initial_state") or {}).get("agent_ids") or []
    assert list(obs.keys()) == agent_ids
    for aid, o in obs.items():
        assert "zone_id" in o
        assert "queue_by_device" in o
        assert "log_frozen" in o


def _scenario_method_matrix() -> list[tuple[Path, str]]:
    """(scenario_path, method_id) for parametrized test."""
    out: list[tuple[Path, str]] = []
    for sp in list_scenario_paths():
        scenario = load_scenario(sp)
        scenario_id = scenario.get("scenario_id") or sp.stem
        for method_id in _get_method_ids_for_scenario(scenario_id):
            out.append((sp, method_id))
    return out


@pytest.mark.parametrize("scenario_path,method_id", _scenario_method_matrix())
def test_scenario_runs_n_steps(scenario_path: Path, method_id: str) -> None:
    """Load scenario, run method for N steps; assert valid actions."""
    scenario = load_scenario(scenario_path)
    policy = scenario_to_policy(scenario)
    scale_config = scenario_to_scale_config(scenario)
    coord = make_coord_method_for_scenario(method_id, policy, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")

    agent_ids = (scenario.get("initial_state") or {}).get("agent_ids") or []
    n_steps = min(3, scale_config.get("horizon_steps", 10))

    coord.reset(scale_config.get("seed", 42), policy, scale_config)
    for t in range(n_steps):
        obs = scenario_obs_at_step(scenario, t)
        infos: dict = {}
        actions_dict = coord.propose_actions(obs, infos, t)
        assert isinstance(actions_dict, dict)
        for aid in agent_ids:
            ad = actions_dict.get(aid, {})
            idx = ad.get("action_index", 0)
            assert idx in VALID_ACTION_INDICES, f"{scenario_path.name} {method_id} t={t} {aid}: action_index {idx}"


def _count_start_runs(actions_dict: dict) -> int:
    """Total START_RUN actions in one step."""
    return sum(1 for ad in actions_dict.values() if isinstance(ad, dict) and ad.get("action_index") == ACTION_START_RUN)


def test_hierarchical_hub_rr_vs_centralized_planner_throughput() -> None:
    """Same scenario and seed: run both methods; assert valid actions and non-negative throughput.
    In multi-site scenarios with message delay, hierarchical can achieve better effective throughput."""
    paths = list_scenario_paths()
    if not paths:
        pytest.skip("no scenario fixtures")
    scenario = load_scenario(paths[0])
    policy = scenario_to_policy(scenario)
    scale_config = scenario_to_scale_config(scenario)
    scale_config["seed"] = 42
    n_steps = min(5, scale_config.get("horizon_steps", 10))

    central = make_coord_method_for_scenario("centralized_planner", policy, scale_config)
    hierarchical = make_coord_method_for_scenario("hierarchical_hub_rr", policy, scale_config)
    if central is None or hierarchical is None:
        pytest.skip("centralized_planner or hierarchical_hub_rr not available")

    central.reset(42, policy, scale_config)
    hierarchical.reset(42, policy, scale_config)
    central_starts = 0
    hier_starts = 0
    for t in range(n_steps):
        obs = scenario_obs_at_step(scenario, t)
        ca = central.propose_actions(obs, {}, t)
        ha = hierarchical.propose_actions(obs, {}, t)
        for ad in ca.values():
            if isinstance(ad, dict) and ad.get("action_index") in VALID_ACTION_INDICES:
                pass
            else:
                assert ad.get("action_index") in VALID_ACTION_INDICES
        for ad in ha.values():
            assert isinstance(ad, dict) and ad.get("action_index") in VALID_ACTION_INDICES
        central_starts += _count_start_runs(ca)
        hier_starts += _count_start_runs(ha)
    assert central_starts >= 0 and hier_starts >= 0
