"""
Router determinism: same seed => identical paths.
"""

from __future__ import annotations

import random

from labtrust_gym.baselines.coordination.routing.graph import RoutingGraph
from labtrust_gym.baselines.coordination.routing.reservations import (
    ReservationTable,
)
from labtrust_gym.baselines.coordination.routing.whca_router import (
    whca_route,
)


def _small_graph() -> RoutingGraph:
    nodes = {"Z0", "Z1", "Z2", "Z3"}
    edges = {("Z0", "Z1"), ("Z1", "Z2"), ("Z2", "Z3"), ("Z1", "Z3")}
    return RoutingGraph(nodes=nodes, edges=edges)


def test_whca_same_seed_same_path() -> None:
    """Same agent, start, goal, seed => same path."""
    graph = _small_graph()
    horizon = 8
    t0 = 0
    res1 = ReservationTable(max_t=t0 + horizon + 1)
    res2 = ReservationTable(max_t=t0 + horizon + 1)
    rng1 = random.Random(99)
    rng2 = random.Random(99)
    path1 = whca_route(
        "a",
        "Z0",
        "Z3",
        t0,
        horizon,
        graph,
        res1,
        rng1,
    )
    path2 = whca_route(
        "a",
        "Z0",
        "Z3",
        t0,
        horizon,
        graph,
        res2,
        rng2,
    )
    assert path1 == path2


def test_whca_different_seed_may_differ() -> None:
    """Different seed can yield different path (when tie-breaks exist)."""
    graph = _small_graph()
    horizon = 8
    t0 = 0
    res1 = ReservationTable(max_t=t0 + horizon + 1)
    res2 = ReservationTable(max_t=t0 + horizon + 1)
    path1 = whca_route(
        "a",
        "Z0",
        "Z3",
        t0,
        horizon,
        graph,
        res1,
        random.Random(1),
    )
    path2 = whca_route(
        "a",
        "Z0",
        "Z3",
        t0,
        horizon,
        graph,
        res2,
        random.Random(2),
    )
    assert path1 is not None
    assert path2 is not None
    assert path1[0] == (t0, "Z0") and path1[-1][1] == "Z3"
    assert path2[0] == (t0, "Z0") and path2[-1][1] == "Z3"
