"""
MAPF property-based test: small zone graphs and (start, goal) pairs.
Run WHCA (and CBS/ECBS when available); assert no collision via invariants.
Uses fixed RNG for reproducibility.
"""

from __future__ import annotations

import random

import pytest

from labtrust_gym.baselines.coordination.routing.graph import RoutingGraph
from labtrust_gym.baselines.coordination.routing.invariants import (
    check_inv_route_001,
    check_swap_collision,
)
from labtrust_gym.baselines.coordination.routing.reservations import ReservationTable
from labtrust_gym.baselines.coordination.routing.whca_router import whca_route_and_reserve


def _make_linear(n: int) -> RoutingGraph:
    """Linear chain: n0-n1-n2-..."""
    nodes = {f"n{i}" for i in range(n)}
    edges = {(f"n{i}", f"n{i + 1}") for i in range(n - 1)}
    return RoutingGraph(nodes=nodes, edges=edges)


def _make_star(center: str, leaves: list[str]) -> RoutingGraph:
    """Star: center connected to each leaf."""
    nodes = {center} | set(leaves)
    edges = {(center, L) for L in leaves} | {(L, center) for L in leaves}
    return RoutingGraph(nodes=nodes, edges=edges)


def _make_grid(rows: int, cols: int) -> RoutingGraph:
    """Grid: (i,j) as node id 'g_i_j', 4-connected."""
    nodes = {f"g_{i}_{j}" for i in range(rows) for j in range(cols)}
    edges: set[tuple[str, str]] = set()
    for i in range(rows):
        for j in range(cols):
            n = f"g_{i}_{j}"
            if i + 1 < rows:
                edges.add((n, f"g_{i + 1}_{j}"))
            if j + 1 < cols:
                edges.add((n, f"g_{i}_{j + 1}"))
    for a, b in list(edges):
        edges.add((b, a))
    return RoutingGraph(nodes=nodes, edges=edges)


def _all_graphs() -> list[tuple[str, RoutingGraph]]:
    """30 small graphs: linear, star, grid 2x3, etc."""
    out: list[tuple[str, RoutingGraph]] = []
    for k in range(2, 9):
        out.append((f"linear_{k}", _make_linear(k)))
    for leaves in (
        ["a", "b", "c"],
        ["u", "v", "w"],
        ["p", "q", "r", "s"],
        ["p", "q", "r", "s", "t"],
        ["a", "b", "c", "d", "e", "f"],
    ):
        out.append((f"star_{len(leaves)}", _make_star("c", leaves)))
    for rows, cols in [(2, 2), (2, 3), (2, 4), (2, 5), (3, 2), (3, 3), (3, 4), (4, 2), (4, 3)]:
        out.append((f"grid_{rows}x{cols}", _make_grid(rows, cols)))
    for k in range(9, 13):
        out.append((f"linear_{k}", _make_linear(k)))
    out.append(("star_7", _make_star("h", ["a", "b", "c", "d", "e", "f", "g"])))
    out.append(("grid_2x6", _make_grid(2, 6)))
    out.append(("grid_5x2", _make_grid(5, 2)))
    out.append(("linear_13", _make_linear(13)))
    out.append(("star_8", _make_star("z", ["a", "b", "c", "d", "e", "f", "g", "h"])))
    return out[:30]


def _node_list(graph: RoutingGraph) -> list[str]:
    return sorted(graph.nodes())


def _generate_start_goal_pairs(
    graph: RoutingGraph,
    rng: random.Random,
    count: int,
) -> list[tuple[str, str]]:
    nodes = _node_list(graph)
    if len(nodes) < 2:
        return []
    pairs: list[tuple[str, str]] = []
    for _ in range(count):
        s, g = rng.sample(nodes, 2)
        pairs.append((s, g))
    return pairs


def _path_to_planned(path: list[tuple[int, str]], agent_id: str) -> tuple[list, list]:
    """Convert path [(t, node), ...] to planned_nodes and planned_moves."""
    planned_nodes = [(agent_id, t, node) for t, node in path]
    planned_moves: list[tuple[str, int, str, str]] = []
    for i in range(len(path) - 1):
        t1, n1 = path[i]
        t2, n2 = path[i + 1]
        if t2 == t1 + 1:
            planned_moves.append((agent_id, t1, n1, n2))
    return planned_nodes, planned_moves


@pytest.fixture(scope="module")
def mapf_graphs() -> list[tuple[str, RoutingGraph]]:
    return _all_graphs()


@pytest.fixture(scope="module")
def mapf_rng() -> random.Random:
    return random.Random(42)


def test_mapf_property_whca_collision_free(
    mapf_graphs: list[tuple[str, RoutingGraph]],
    mapf_rng: random.Random,
) -> None:
    """
    Over 30 small graphs and 200+ (start, goal) runs, WHCA produces paths
    that satisfy INV-ROUTE-001 and INV-ROUTE-SWAP (no swap).
    """
    total_runs = 0
    horizon = 16
    for name, graph in mapf_graphs:
        nodes = _node_list(graph)
        if len(nodes) < 2:
            continue
        # Multiple single-agent runs per graph (no multi-agent collision possible)
        pairs = _generate_start_goal_pairs(graph, mapf_rng, 7)
        for start, goal in pairs:
            rng = random.Random(mapf_rng.randint(0, 2**31 - 1))
            reservations = ReservationTable(max_t=horizon + 2)
            path = whca_route_and_reserve(
                "agent_0",
                start,
                goal,
                t0=0,
                horizon=horizon,
                graph=graph,
                reservations=reservations,
                rng=rng,
                zone_order=nodes,
            )
            if path:
                pn, pm = _path_to_planned(path, "agent_0")
                v001 = check_inv_route_001(pn)
                v003 = check_swap_collision(pm)
                assert not v001, f"{name} ({start}->{goal}): INV-ROUTE-001: {v001}"
                assert not v003, f"{name} ({start}->{goal}): INV-ROUTE-SWAP: {v003}"
            total_runs += 1
    assert total_runs >= 200, f"Expected at least 200 runs, got {total_runs}"


def test_mapf_property_whca_multi_agent_collision_free(
    mapf_rng: random.Random,
) -> None:
    """
    Multi-agent: 2–4 agents on same graph with WHCA and shared reservation table;
    combined planned_nodes/planned_moves must pass INV-ROUTE-001 and swap check.
    """
    graph = _make_grid(2, 3)
    nodes = _node_list(graph)
    horizon = 20
    num_agents = 3
    agent_starts_goals: list[tuple[str, str]] = []
    for i in range(num_agents):
        s, g = mapf_rng.sample(nodes, 2)
        agent_starts_goals.append((s, g))
    reservations = ReservationTable(max_t=horizon + 2)
    all_planned_nodes: list[tuple[str, int, str]] = []
    all_planned_moves: list[tuple[str, int, str, str]] = []
    for i, (start, goal) in enumerate(agent_starts_goals):
        aid = f"agent_{i}"
        rng = random.Random(42 + i)
        path = whca_route_and_reserve(
            aid,
            start,
            goal,
            t0=0,
            horizon=horizon,
            graph=graph,
            reservations=reservations,
            rng=rng,
            zone_order=nodes,
        )
        if path:
            pn, pm = _path_to_planned(path, aid)
            all_planned_nodes.extend(pn)
            all_planned_moves.extend(pm)
    if all_planned_nodes:
        v001 = check_inv_route_001(all_planned_nodes)
        v003 = check_swap_collision(all_planned_moves)
        assert not v001, f"INV-ROUTE-001: {v001}"
        assert not v003, f"INV-ROUTE-SWAP: {v003}"


@pytest.mark.skip(reason="CBS not in [mapf]; add when CBS backend available.")
def test_mapf_cbs_equivalence() -> None:
    """Placeholder: when CBS is available, same instance WHCA vs CBS, CBS cost <= WHCA, both collision-free. Blocked on [mapf] CBS backend."""
    pass
