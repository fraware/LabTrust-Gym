"""
WHCA*: no two agents occupy same (t, node) in planned paths (INV-ROUTE-001).
Small graph, many agents; plan in order and assert no conflicts.
"""

from __future__ import annotations

import random

from labtrust_gym.baselines.coordination.routing.graph import RoutingGraph
from labtrust_gym.baselines.coordination.routing.invariants import (
    check_inv_route_001,
)
from labtrust_gym.baselines.coordination.routing.reservations import (
    ReservationTable,
)
from labtrust_gym.baselines.coordination.routing.whca_router import (
    whca_route_and_reserve,
)


def _line_graph(n: int) -> RoutingGraph:
    """Linear chain Z0-Z1-...-Z(n-1)."""
    nodes = {f"Z{i}" for i in range(n)}
    edges = {(f"Z{i}", f"Z{i + 1}") for i in range(n - 1)}
    return RoutingGraph(nodes=nodes, edges=edges)


def test_whca_no_collisions_small_graph() -> None:
    """Five nodes, several agents; plan paths and check INV-ROUTE-001."""
    graph = _line_graph(5)
    rng = random.Random(42)
    horizon = 10
    t0 = 0
    max_t = t0 + horizon + 1
    reservations = ReservationTable(max_t=max_t)
    zone_order = ["Z0", "Z1", "Z2", "Z3", "Z4"]
    agents_goals = [
        ("a1", "Z0", "Z4"),
        ("a2", "Z0", "Z2"),
        ("a3", "Z4", "Z0"),
        ("a4", "Z2", "Z4"),
    ]
    planned: list[tuple[str, int, str]] = []
    for agent_id, start, goal in agents_goals:
        path = whca_route_and_reserve(
            agent_id,
            start,
            goal,
            t0,
            horizon,
            graph,
            reservations,
            rng,
            zone_order=zone_order,
        )
        for t, node in path:
            planned.append((agent_id, t, node))
    violations = check_inv_route_001(planned)
    assert not violations, f"INV-ROUTE-001 violations: {violations}"


def test_whca_no_collisions_many_agents() -> None:
    """Grid-like graph, 20 agents; plan in deterministic order, no conflicts."""
    nodes = {f"Z{i}" for i in range(12)}
    edges = set()
    for i in range(3):
        for j in range(4):
            n = i * 4 + j
            if j < 3:
                edges.add((f"Z{n}", f"Z{n + 1}"))
                edges.add((f"Z{n + 1}", f"Z{n}"))
            if i < 2:
                edges.add((f"Z{n}", f"Z{n + 4}"))
                edges.add((f"Z{n + 4}", f"Z{n}"))
    graph = RoutingGraph(nodes=nodes, edges=edges)
    rng = random.Random(123)
    horizon = 15
    t0 = 0
    reservations = ReservationTable(max_t=t0 + horizon + 1)
    zone_list = sorted(nodes)
    starts = ["Z0", "Z0", "Z1", "Z2", "Z3", "Z4", "Z5", "Z8", "Z9", "Z10"]
    goals = ["Z11", "Z10", "Z11", "Z8", "Z0", "Z11", "Z0", "Z0", "Z11", "Z0"]
    planned = []
    for i, (start, goal) in enumerate(zip(starts, goals)):
        agent_id = f"agent_{i}"
        path = whca_route_and_reserve(
            agent_id,
            start,
            goal,
            t0,
            horizon,
            graph,
            reservations,
            rng,
            zone_order=zone_list,
        )
        for t, node in path:
            planned.append((agent_id, t, node))
    violations = check_inv_route_001(planned)
    assert not violations, f"INV-ROUTE-001: {violations}"
