"""
Auction allocator respects RBAC: only agents whose role allows START_RUN can be assigned work.
Token: agents without TOKEN_RESTRICTED_ENTRY cannot be assigned work in restricted zones.
"""

from __future__ import annotations

import random

from labtrust_gym.baselines.coordination.allocation.auction import (
    AuctionAllocator,
    agent_can_start_run_at_device,
)
from labtrust_gym.baselines.coordination.coordination_kernel import KernelContext
from labtrust_gym.baselines.coordination.decision_types import AllocationDecision


def _policy_rbac_analytics_only() -> dict:
    """RBAC: only A_ANALYTICS has START_RUN; A_QC does not."""
    return {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}],
            "device_placement": [
                {"device_id": "D1", "zone_id": "Z_A"},
                {"device_id": "D2", "zone_id": "Z_B"},
            ],
            "graph_edges": [{"from": "Z_A", "to": "Z_B"}],
        },
        "rbac_policy": {
            "version": "0.1",
            "roles": {
                "ROLE_ANALYTICS": {
                    "allowed_actions": ["TICK", "MOVE", "START_RUN", "END_RUN"],
                },
                "ROLE_QC": {
                    "allowed_actions": ["TICK", "MOVE", "QC_EVENT"],
                },
            },
            "agents": {
                "A_ANALYTICS": "ROLE_ANALYTICS",
                "A_QC": "ROLE_QC",
            },
        },
    }


def test_auction_assigns_only_to_agent_with_start_run_role() -> None:
    """Only agent with role that allows START_RUN receives work."""
    policy = _policy_rbac_analytics_only()
    scale_config: dict = {}
    obs = {
        "A_ANALYTICS": {
            "zone_id": "Z_A",
            "queue_has_head": [1, 0],
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        },
        "A_QC": {
            "zone_id": "Z_A",
            "queue_has_head": [1, 0],
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        },
    }
    infos: dict = {}
    rng = random.Random(42)
    ctx = KernelContext(
        obs=obs,
        infos=infos,
        t=0,
        policy=policy,
        scale_config=scale_config,
        seed=42,
        rng=rng,
    )
    allocator = AuctionAllocator(max_bids=2)
    decision = allocator.allocate(ctx)
    assert isinstance(decision, AllocationDecision)
    assignments = decision.assignments
    agent_ids_assigned = {a[0] for a in assignments}
    assert "A_QC" not in agent_ids_assigned
    assert agent_ids_assigned <= {"A_ANALYTICS"}


def test_agent_can_start_run_at_device_respects_rbac() -> None:
    """agent_can_start_run_at_device returns False when role lacks START_RUN."""
    policy = _policy_rbac_analytics_only()
    restricted = set()
    obs_analytics = {"zone_id": "Z_A", "token_active": {}}
    obs_qc = {"zone_id": "Z_A", "token_active": {}}
    assert agent_can_start_run_at_device("A_ANALYTICS", "D1", "Z_A", policy, obs_analytics, restricted) is True
    assert agent_can_start_run_at_device("A_QC", "D1", "Z_A", policy, obs_qc, restricted) is False


def test_agent_can_start_run_at_device_restricted_zone_requires_token() -> None:
    """In restricted zone, agent must have TOKEN_RESTRICTED_ENTRY to be allowed."""
    policy = {
        "rbac_policy": {
            "roles": {"ROLE_ANALYTICS": {"allowed_actions": ["START_RUN"]}},
            "agents": {"A1": "ROLE_ANALYTICS"},
        },
    }
    restricted = {"Z_RESTRICTED_BIOHAZARD"}
    obs_no_token = {"zone_id": "Z_A", "token_active": {}}
    obs_with_token = {
        "zone_id": "Z_A",
        "token_active": {"TOKEN_RESTRICTED_ENTRY": True},
    }
    assert (
        agent_can_start_run_at_device("A1", "D1", "Z_RESTRICTED_BIOHAZARD", policy, obs_no_token, restricted) is False
    )
    assert (
        agent_can_start_run_at_device("A1", "D1", "Z_RESTRICTED_BIOHAZARD", policy, obs_with_token, restricted) is True
    )
