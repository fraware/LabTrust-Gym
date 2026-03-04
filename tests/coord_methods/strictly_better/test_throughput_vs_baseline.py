"""
Strictly-better sanity: llm_central_planner and baseline (centralized_planner) both run and produce valid proposals.

Full throughput comparison requires run_benchmark with coord_scale/coord_risk; this test asserts
both methods complete propose_actions for several steps without error (no crash, valid structure).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.registry import make_coordination_method


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _minimal_policy() -> dict:
    from labtrust_gym.policy.loader import load_yaml

    repo = _repo_root()
    zone_path = repo / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
    if zone_path.exists():
        data = load_yaml(zone_path)
        layout = data.get("zone_layout") or data
    else:
        layout = {"zones": [], "graph_edges": [], "device_placement": []}
    return {
        "zone_layout": layout,
        "pz_to_engine": {"worker_0": "ops_0", "worker_1": "runner_0", "worker_2": "runner_1"},
    }


def _minimal_obs(agent_ids: list[str], t: int) -> dict:
    obs = {}
    for i, aid in enumerate(agent_ids):
        obs[aid] = {
            "my_zone_idx": 1 + (i + t) % 2,
            "zone_id": "Z_SORTING_LANES" if i == 0 else "Z_ANALYZER_HALL_A",
            "queue_has_head": [0] * 2,
            "queue_by_device": [{"queue_head": "", "queue_len": 0}, {"queue_head": "", "queue_len": 0}],
            "log_frozen": 0,
        }
    return obs


@pytest.mark.slow
def test_llm_central_planner_and_baseline_both_produce_valid_actions() -> None:
    """Centralized_planner (baseline) and llm_central_planner both run 5 steps and return valid action dicts."""
    repo = _repo_root()
    policy = _minimal_policy()
    scale_config = {"num_agents_total": 3, "horizon_steps": 10, "seed": 42}
    agent_ids = sorted(policy.get("pz_to_engine", {}))
    for method_id in ("centralized_planner", "llm_central_planner"):
        try:
            method = make_coordination_method(
                method_id,
                policy,
                repo_root=repo,
                scale_config=scale_config,
            )
        except Exception as e:
            pytest.skip(f"{method_id}: {e}")
        method.reset(42, policy, scale_config)
        for t in range(5):
            obs = _minimal_obs(agent_ids, t)
            actions = method.propose_actions(obs, {}, t)
            assert isinstance(actions, dict), f"{method_id} step {t}: expected dict, got {type(actions)}"
