"""
Routing invariant contract tests: known-good and known-bad plans for INV-ROUTE-001/002/SWAP.
Also tests that a plan using a restricted edge without token is rejected by check_inv_route_002
and by simplex validate_plan (shield).
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.decision_types import RouteDecision
from labtrust_gym.baselines.coordination.routing.invariants import (
    INV_ROUTE_001,
    INV_ROUTE_002,
    INV_ROUTE_SWAP,
    check_inv_route_001,
    check_inv_route_002,
    check_swap_collision,
)


def test_invariant_contract_known_good_plan() -> None:
    """All three checks pass on a known-good plan: distinct nodes at same t, no restricted edge without token, no swap."""
    planned_nodes = [
        ("a1", 0, "Z1"),
        ("a2", 0, "Z2"),
        ("a1", 1, "Z2"),
        ("a2", 1, "Z1"),
    ]
    planned_moves = [
        ("a1", 0, "Z1", "Z2"),
        ("a2", 0, "Z2", "Z1"),
    ]
    # No swap at same t: a1 moves Z1->Z2 at t=0, a2 moves Z2->Z1 at t=0 -> swap. So use different t.
    planned_moves_ok = [
        ("a1", 0, "Z1", "Z2"),
        ("a2", 1, "Z2", "Z1"),
    ]
    restricted_edges: set[tuple[str, str]] = set()
    agent_has_token: dict[str, bool] = {"a1": False, "a2": False}

    v001 = check_inv_route_001(planned_nodes)
    v002 = check_inv_route_002(planned_moves_ok, restricted_edges, agent_has_token)
    v003 = check_swap_collision(planned_moves_ok)
    assert not v001, f"INV-ROUTE-001: {v001}"
    assert not v002, f"INV-ROUTE-002: {v002}"
    assert not v003, f"INV-ROUTE-SWAP: {v003}"


def test_invariant_contract_known_bad_001() -> None:
    """Known-bad plan: two agents same (t, node) -> INV-ROUTE-001 violation."""
    planned_nodes = [
        ("a1", 0, "Z1"),
        ("a2", 0, "Z1"),
    ]
    v = check_inv_route_001(planned_nodes)
    assert len(v) >= 1
    assert INV_ROUTE_001 in v[0]
    assert "Z1" in v[0] and "a1" in v[0] and "a2" in v[0]


def test_invariant_contract_known_bad_002() -> None:
    """Known-bad plan: agent uses restricted edge without token -> INV-ROUTE-002 violation."""
    planned_moves = [("a1", 0, "Z1", "Z2")]
    restricted_edges = {("Z1", "Z2")}
    agent_has_token = {"a1": False}
    v = check_inv_route_002(planned_moves, restricted_edges, agent_has_token)
    assert len(v) >= 1
    assert INV_ROUTE_002 in v[0]
    assert "restricted" in v[0].lower() or "Z1" in v[0]


def test_invariant_contract_known_bad_swap() -> None:
    """Known-bad plan: swap collision at same t -> INV-ROUTE-SWAP violation."""
    planned_moves = [
        ("a", 0, "Z1", "Z2"),
        ("b", 0, "Z2", "Z1"),
    ]
    v = check_swap_collision(planned_moves)
    assert len(v) >= 1
    assert INV_ROUTE_SWAP in v[0]
    assert "swap" in v[0].lower()


def test_invariant_002_restricted_edge_without_token_shield_rejects() -> None:
    """Plan that uses restricted edge without token is rejected by check_inv_route_002 and by validate_plan (shield)."""
    from labtrust_gym.baselines.coordination.assurance.simplex import validate_plan

    # Route: agent a1 MOVE from Z1 to Z2; policy has restricted edge (Z1, Z2); obs has no token for a1.
    route = RouteDecision(
        per_agent=(("a1", "MOVE", (("from_zone", "Z1"), ("to_zone", "Z2"))),),
        explain="test",
    )
    # Policy with zone_layout_policy containing zones and a door requiring token for Z1<->Z2
    policy = {
        "zone_layout_policy": {
            "zones": [
                {"zone_id": "Z1"},
                {"zone_id": "Z2", "restricted": True},
            ],
            "graph_edges": [{"from": "Z1", "to": "Z2", "via_door": "D1"}],
            "doors": [{"door_id": "D1", "requires_token": True}],
        },
    }
    obs = {
        "a1": {
            "zone_id": "Z1",
            "token_active": {},
        },
    }
    device_zone: dict[str, str] = {}

    from types import SimpleNamespace
    context = SimpleNamespace(
        policy=policy,
        obs=obs,
        t=0,
        device_zone=device_zone,
        agent_ids=["a1"],
    )

    # check_inv_route_002: build planned_moves and restricted_edges the same way as shield
    from labtrust_gym.baselines.coordination.routing.graph import build_routing_graph

    layout = policy.get("zone_layout") or policy.get("zone_layout_policy") or {}
    graph = build_routing_graph(layout)
    restricted_edges = graph.restricted_edges_set
    agent_has_token = {"a1": False}
    planned_moves = [("a1", 0, "Z1", "Z2")]
    v002 = check_inv_route_002(planned_moves, restricted_edges, agent_has_token)
    assert len(v002) >= 1, "check_inv_route_002 should flag restricted edge without token"
    assert INV_ROUTE_002 in v002[0]

    result = validate_plan(route, context)
    assert not result.ok, "validate_plan (shield) should reject restricted edge without token"
    assert result.counters.get("restricted", 0) >= 1
    assert any(INV_ROUTE_002 in r for r in result.reasons)
