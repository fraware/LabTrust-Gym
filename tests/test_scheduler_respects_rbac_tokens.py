"""
Scheduler kernel never proposes illegal actions: RBAC and token constraints.

Under strict mode (policy with RBAC that denies START_RUN for some agents, or
restricted zone without token), the composed method must not output START_RUN
for those (agent, device) pairs.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.baselines.coordination.compose import build_kernel_context
from labtrust_gym.baselines.coordination.registry import make_coordination_method


def _policy_rbac_qc_no_start_run() -> dict:
    """RBAC: ROLE_QC has no START_RUN; ROLE_RUNNER has START_RUN."""
    return {
        "zone_layout": {
            "zones": [
                {"zone_id": "Z_SORTING_LANES"},
                {"zone_id": "Z_ANALYZER_HALL_A"},
            ],
            "device_placement": [
                {"device_id": "D1", "zone_id": "Z_ANALYZER_HALL_A"},
                {"device_id": "D2", "zone_id": "Z_ANALYZER_HALL_A"},
            ],
            "graph_edges": [{"from": "Z_SORTING_LANES", "to": "Z_ANALYZER_HALL_A"}],
        },
        "rbac_policy": {
            "version": "0.1",
            "roles": {
                "ROLE_RUNNER": {
                    "allowed_actions": ["TICK", "MOVE", "START_RUN", "QUEUE_RUN"],
                },
                "ROLE_QC": {
                    "allowed_actions": ["TICK", "MOVE", "QC_EVENT"],
                },
            },
            "agents": {
                "worker_0": "ROLE_RUNNER",
                "worker_1": "ROLE_QC",
            },
        },
    }


def test_kernel_scheduler_or_never_start_run_for_rbac_denied_agent() -> None:
    """With RBAC denying START_RUN for worker_1, no START_RUN action for worker_1."""
    repo = Path(__file__).resolve().parent.parent
    policy = _policy_rbac_qc_no_start_run()
    method = make_coordination_method(
        "kernel_scheduler_or",
        policy=policy,
        repo_root=repo,
        scale_config={"num_agents_total": 2},
    )
    method.reset(seed=7, policy=policy, scale_config={})
    obs = {
        "worker_0": {
            "my_zone_idx": 2,
            "zone_id": "Z_ANALYZER_HALL_A",
            "queue_has_head": [1, 0],
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        },
        "worker_1": {
            "my_zone_idx": 2,
            "zone_id": "Z_ANALYZER_HALL_A",
            "queue_has_head": [1, 0],
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
                {"device_id": "D2", "queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        },
    }
    infos: dict = {}
    ctx = build_kernel_context(obs, infos, 0, policy, {}, 7)
    actions, _ = method.step(ctx)
    assert actions["worker_1"]["action_index"] != 3
    if actions["worker_1"].get("action_type") == "START_RUN":
        raise AssertionError("worker_1 (ROLE_QC) must not get START_RUN")
    assert "worker_1" in actions
    assert actions["worker_1"].get("action_type") != "START_RUN"


def test_kernel_scheduler_or_restricted_zone_requires_token() -> None:
    """Agent in restricted zone without token must not get START_RUN there."""
    policy = {
        "zone_layout": {
            "zones": [
                {"zone_id": "Z_A"},
                {"zone_id": "Z_RESTRICTED_BIOHAZARD", "restricted": True},
            ],
            "device_placement": [
                {"device_id": "D1", "zone_id": "Z_RESTRICTED_BIOHAZARD"},
            ],
            "graph_edges": [{"from": "Z_A", "to": "Z_RESTRICTED_BIOHAZARD"}],
        },
        "rbac_policy": {
            "version": "0.1",
            "roles": {
                "ROLE_RUNNER": {
                    "allowed_actions": ["TICK", "MOVE", "START_RUN"],
                },
            },
            "agents": {"worker_0": "ROLE_RUNNER"},
        },
    }
    repo = Path(__file__).resolve().parent.parent
    method = make_coordination_method(
        "kernel_scheduler_or",
        policy=policy,
        repo_root=repo,
        scale_config={"num_agents_total": 1},
    )
    method.reset(seed=11, policy=policy, scale_config={})
    obs = {
        "worker_0": {
            "zone_id": "Z_RESTRICTED_BIOHAZARD",
            "queue_has_head": [1],
            "queue_by_device": [
                {"device_id": "D1", "queue_head": "W1", "queue_len": 1},
            ],
            "log_frozen": 0,
            "token_active": {},
        },
    }
    infos = {}
    ctx = build_kernel_context(obs, infos, 0, policy, {}, 11)
    actions, _ = method.step(ctx)
    assert actions["worker_0"].get("action_type") != "START_RUN"
