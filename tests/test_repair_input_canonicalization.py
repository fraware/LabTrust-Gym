"""
Unit tests: repair input canonicalization is stable (same input -> same JSON -> same hash).
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.repair_input import (
    build_repair_input,
    repair_input_hash,
)


def test_repair_input_hash_stable_for_same_logical_input() -> None:
    """Same logical content in different key order produces same hash."""
    scale_a = {"num_agents": 2, "num_sites": 1}
    scale_b = {"num_sites": 1, "num_agents": 2}
    plan = {"route_hash": "abc", "step_idx": 0}
    blocked = [{"agent_id": "a1", "action_type": "MOVE", "reason_code": "COLLISION"}]
    constraint = {"allowed_actions": ["NOOP", "MOVE"], "invariants": ["INV-001"]}

    inp1 = build_repair_input(
        scale_config_snapshot=scale_a,
        last_accepted_plan_summary=plan,
        blocked_actions=blocked,
        constraint_summary=constraint,
        red_team_flags=["comms_poison"],
    )
    inp2 = build_repair_input(
        scale_config_snapshot=scale_b,
        last_accepted_plan_summary=plan,
        blocked_actions=blocked,
        constraint_summary=constraint,
        red_team_flags=["comms_poison"],
    )
    assert repair_input_hash(inp1) == repair_input_hash(inp2)


def test_repair_input_hash_different_input_different_hash() -> None:
    """Different logical content produces different hash."""
    scale = {"num_agents": 2}
    plan = {"step_idx": 0}
    constraint = {"allowed_actions": ["NOOP"]}

    inp1 = build_repair_input(
        scale_config_snapshot=scale,
        last_accepted_plan_summary=plan,
        blocked_actions=[],
        constraint_summary=constraint,
        red_team_flags=[],
    )
    inp2 = build_repair_input(
        scale_config_snapshot={**scale, "num_agents": 3},
        last_accepted_plan_summary=plan,
        blocked_actions=[],
        constraint_summary=constraint,
        red_team_flags=[],
    )
    assert repair_input_hash(inp1) != repair_input_hash(inp2)


def test_repair_input_blocked_actions_sorted() -> None:
    """Blocked actions are normalized to stable order."""
    blocked = [
        {"agent_id": "b", "action_type": "MOVE", "reason_code": "R2"},
        {"agent_id": "a", "action_type": "NOOP", "reason_code": "R1"},
    ]
    inp = build_repair_input(
        scale_config_snapshot={},
        last_accepted_plan_summary={},
        blocked_actions=blocked,
        constraint_summary={},
        red_team_flags=None,
    )
    order = [x["agent_id"] for x in inp["blocked_actions"]]
    assert order == ["a", "b"]
