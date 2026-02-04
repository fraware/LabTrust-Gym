"""
Bid spoof risk (INJ-BID-SPOOF-001) and bid anomaly detector: detector flags outlier low bids
and triggers containment (ignore bids from agent for K steps); emits and reason code.
"""

from __future__ import annotations

import random

from labtrust_gym.baselines.coordination.allocation.auction import (
    BID_FORBIDDEN,
    INJ_BID_SPOOF_001,
    REASON_CODE_BID_ANOMALY,
    AuctionAllocator,
    detect_bid_anomalies,
)
from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext


def _minimal_obs_and_policy(
    agent_ids: list[str],
    device_ids: list[str],
    zone_id: str,
):
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": zone_id}],
            "device_placement": [
                {"device_id": d, "zone_id": zone_id} for d in device_ids
            ],
            "graph_edges": [],
        },
    }
    obs = {}
    for aid in agent_ids:
        obs[aid] = {
            "zone_id": zone_id,
            "queue_has_head": [1] * len(device_ids),
            "queue_by_device": [
                {"device_id": d, "queue_head": f"W_{d}", "queue_len": 1}
                for d in device_ids
            ],
            "log_frozen": 0,
        }
    return obs, policy


def test_detect_bid_anomalies_flags_low_bid() -> None:
    """Detector flags agent whose winning bid is below mean - 2*std."""
    bids_used = [
        ("A1", "W1", 0.5),
        ("A2", "W2", 10.0),
        ("A3", "W3", 11.0),
        ("A4", "W4", 12.0),
    ]
    excluded, emits = detect_bid_anomalies(bids_used, threshold_std=0.5)
    assert "A1" in excluded
    assert len(emits) >= 1
    assert any(
        e.get("agent_id") == "A1" and e.get("reason_code") == REASON_CODE_BID_ANOMALY
        for e in emits
    )


def test_detect_bid_anomalies_no_anomaly_when_bids_similar() -> None:
    """When all bids are similar, no agent is flagged."""
    bids_used = [("A1", "W1", 10.0), ("A2", "W2", 10.5), ("A3", "W3", 11.0)]
    excluded, emits = detect_bid_anomalies(bids_used, threshold_std=2.0)
    assert len(excluded) == 0
    assert len(emits) == 0


def test_inj_bid_spoof_001_spoofing_agent_wins_without_detector() -> None:
    """With INJ-BID-SPOOF-001 and detector disabled, spoofing agent wins (low bid)."""
    agent_ids = ["A1", "A2", "A3"]
    obs, policy = _minimal_obs_and_policy(agent_ids, ["D1"], "Z_A")
    scale_config = {"injection_id": INJ_BID_SPOOF_001}
    rng = random.Random(99)
    ctx = KernelContext(
        obs=obs,
        infos={},
        t=0,
        policy=policy,
        scale_config=scale_config,
        seed=99,
        rng=rng,
    )
    allocator = AuctionAllocator(max_bids=3, detector_enabled=False)
    decision = allocator.allocate(ctx)
    assigned_agents = [a[0] for a in decision.assignments]
    assert (
        "A1" in assigned_agents
    ), "spoofing agent (first in sorted order) should win with detector off"


def test_inj_bid_spoof_001_detector_emits_and_containment_reduces_spoof_wins() -> None:
    """With detector enabled, spoofing agent is flagged (emit) and then contained for K steps."""
    agent_ids = ["A1", "A2", "A3"]
    obs, policy = _minimal_obs_and_policy(agent_ids, ["D1", "D2"], "Z_A")
    scale_config = {"injection_id": INJ_BID_SPOOF_001}
    allocator = AuctionAllocator(max_bids=3, detector_enabled=True, containment_steps=5)

    ctx0 = KernelContext(
        obs=obs,
        infos={},
        t=0,
        policy=policy,
        scale_config=scale_config,
        seed=100,
        rng=random.Random(100),
    )
    decision0 = allocator.allocate(ctx0)
    metrics0 = allocator.get_alloc_metrics()
    alloc_emits = metrics0.get("alloc_emits") or []
    has_anomaly_emit = any(
        e.get("emit") == "BID_ANOMALY_DETECTED"
        and e.get("reason_code") == REASON_CODE_BID_ANOMALY
        for e in alloc_emits
    )
    assert (
        has_anomaly_emit
    ), "detector should emit BID_ANOMALY_DETECTED for spoofed low bid"

    ctx1 = KernelContext(
        obs=obs,
        infos={},
        t=1,
        policy=policy,
        scale_config=scale_config,
        seed=100,
        rng=random.Random(101),
    )
    decision1 = allocator.allocate(ctx1)
    assigned_step1 = [a[0] for a in decision1.assignments]
    assert (
        "A1" not in assigned_step1
    ), "containment should exclude spoofing agent on next step(s)"


def test_taskh_auction_bid_spoof_smoke(tmp_path) -> None:
    """TaskH with kernel_auction_edf and INJ-BID-SPOOF-001 runs; results have coordination.alloc (smoke)."""
    import json
    from pathlib import Path

    import pytest

    from labtrust_gym.benchmarks.runner import run_benchmark

    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root with policy not found")
    out = tmp_path / "results_taskh_auction.json"
    run_benchmark(
        task_name="TaskH_COORD_RISK",
        num_episodes=1,
        base_seed=99,
        out_path=out,
        repo_root=repo,
        coord_method="kernel_auction_edf",
        injection_id="INJ-BID-SPOOF-001",
    )
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    episodes = data.get("episodes") or []
    assert len(episodes) >= 1
    metrics = episodes[0].get("metrics") or {}
    coord = metrics.get("coordination") or {}
    alloc = coord.get("alloc") or {}
    assert (
        "mean_bid" in alloc
        or "num_assignments" in alloc
        or "gini_work_distribution" in alloc
    )


def test_bid_forbidden_not_used_as_winning_bid() -> None:
    """Bids at or above BID_FORBIDDEN are never selected as winning."""
    from labtrust_gym.baselines.coordination.allocation.auction import (
        run_auction,
        WorkItem,
    )

    items = [WorkItem("W1", "D1", "Z_A", 1)]
    agents = ["A1", "A2"]

    def bid_fn(agent_id: str, item: WorkItem) -> float:
        if agent_id == "A1":
            return 5.0
        return BID_FORBIDDEN

    rng = random.Random(1)
    assignments, bids_used, _ = run_auction(items, agents, bid_fn, max_bids=2, rng=rng)
    assert len(assignments) == 1
    assert assignments[0][0] == "A1"
    assert bids_used[0][2] < BID_FORBIDDEN
