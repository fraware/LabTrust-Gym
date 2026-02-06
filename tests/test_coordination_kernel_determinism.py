"""
Determinism: same seed yields identical decision hashes and per-agent actions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from labtrust_gym.baselines.coordination.compose import (
    build_kernel_context,
    compose_kernel,
)
from labtrust_gym.baselines.coordination.kernel_components import (
    CentralizedAllocator,
    EDFScheduler,
    TrivialRouter,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _minimal_policy() -> dict:
    from labtrust_gym.policy.loader import load_yaml

    root = _repo_root()
    zone_path = root / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
    if not zone_path.exists():
        return {"zone_layout": {"zones": [], "graph_edges": [], "device_placement": []}}
    data = load_yaml(zone_path)
    layout = data.get("zone_layout") or data
    return {"zone_layout": layout}


def _minimal_obs(agent_ids: list, t: int) -> dict:
    obs = {}
    for i, aid in enumerate(agent_ids):
        obs[aid] = {
            "my_zone_idx": 1 + (i + t) % 2,
            "zone_id": "Z_SORTING_LANES" if i == 0 else "Z_ANALYZER_HALL_A",
            "queue_has_head": [0] * 2,
            "queue_by_device": [
                {"queue_head": "", "queue_len": 0},
                {"queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        }
    return obs


def test_kernel_same_seed_same_decision_hashes_and_actions() -> None:
    """Same seed and context => identical decision hashes and action dicts."""
    policy = _minimal_policy()
    scale_config = {"num_agents_total": 2, "horizon_steps": 10}
    agent_ids = ["worker_0", "worker_1"]
    seed = 42

    method = compose_kernel(
        CentralizedAllocator(compute_budget=2),
        EDFScheduler(),
        TrivialRouter(),
        "kernel_centralized_edf",
    )
    method.reset(seed, policy, scale_config)

    obs1 = _minimal_obs(agent_ids, 0)
    obs2 = _minimal_obs(agent_ids, 0)
    infos = {}
    ctx1 = build_kernel_context(obs1, infos, 0, policy, scale_config, seed)
    ctx2 = build_kernel_context(obs2, infos, 0, policy, scale_config, seed)

    actions1, decision1 = method.step(ctx1)
    actions2, decision2 = method.step(ctx2)

    assert decision1 is not None
    assert decision2 is not None
    assert decision1.state_hash == decision2.state_hash
    assert decision1.allocation_hash == decision2.allocation_hash
    assert decision1.schedule_hash == decision2.schedule_hash
    assert decision1.route_hash == decision2.route_hash

    payload1 = json.dumps(actions1, sort_keys=True)
    payload2 = json.dumps(actions2, sort_keys=True)
    assert hashlib.sha256(payload1.encode()).hexdigest() == hashlib.sha256(payload2.encode()).hexdigest()


def test_kernel_same_seed_same_actions_across_steps() -> None:
    """Run 5 steps twice with same seed; action sequences must match."""
    policy = _minimal_policy()
    scale_config = {"num_agents_total": 2, "horizon_steps": 10}
    agent_ids = ["worker_0", "worker_1"]
    seed = 12345

    method = compose_kernel(
        CentralizedAllocator(2),
        EDFScheduler(),
        TrivialRouter(),
        "kernel_centralized_edf",
    )
    method.reset(seed, policy, scale_config)

    hashes1 = []
    actions_ser1 = []
    for t in range(5):
        obs = _minimal_obs(agent_ids, t)
        ctx = build_kernel_context(obs, {}, t, policy, scale_config, seed)
        actions, decision = method.step(ctx)
        hashes1.append(
            (decision.allocation_hash, decision.schedule_hash, decision.route_hash) if decision else (None, None, None)
        )
        actions_ser1.append(json.dumps(actions, sort_keys=True))

    method.reset(seed, policy, scale_config)
    hashes2 = []
    actions_ser2 = []
    for t in range(5):
        obs = _minimal_obs(agent_ids, t)
        ctx = build_kernel_context(obs, {}, t, policy, scale_config, seed)
        actions, decision = method.step(ctx)
        hashes2.append(
            (decision.allocation_hash, decision.schedule_hash, decision.route_hash) if decision else (None, None, None)
        )
        actions_ser2.append(json.dumps(actions, sort_keys=True))

    assert hashes1 == hashes2
    assert actions_ser1 == actions_ser2
