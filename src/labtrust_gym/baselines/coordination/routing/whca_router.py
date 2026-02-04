"""
Windowed Cooperative A* (WHCA*): plan path over horizon H avoiding reservation table.
Deterministic tie-breaks via rng; no external MAPF libs.
"""

from __future__ import annotations

import heapq
from typing import Any, Callable, List, Optional, Set, Tuple

from labtrust_gym.baselines.coordination.routing.graph import RoutingGraph
from labtrust_gym.baselines.coordination.routing.reservations import (
    ReservationTable,
)


def _manhattan_heuristic(
    node: str,
    goal: str,
    zone_order: Optional[List[str]],
) -> int:
    """Heuristic: 0 if node==goal else 1 (topological graph, no coordinates)."""
    if node == goal:
        return 0
    if zone_order:
        try:
            i = zone_order.index(node)
            j = zone_order.index(goal)
            return abs(i - j)
        except ValueError:
            pass
    return 1


def whca_route(
    agent_id: str,
    start: str,
    goal: str,
    t0: int,
    horizon: int,
    graph: RoutingGraph,
    reservations: ReservationTable,
    rng: Any,
    has_restricted_token: bool = False,
    zone_order: Optional[List[str]] = None,
) -> List[Tuple[int, str]]:
    """
    Plan path from (t0, start) to (t, goal) with t in [t0, t0+horizon].
    A* over (t, node); edge cost 1 time step; avoids (t, n) already reserved by another.
    INV-ROUTE-002: never use restricted edge unless has_restricted_token.
    Returns path as [(t, node), ...] including (t0, start); empty if no path.
    Deterministic: neighbor order sorted and tie-break by rng.
    """
    if start not in graph.nodes() or goal not in graph.nodes():
        return []
    if start == goal:
        return [(t0, start)]

    max_t = min(t0 + horizon, reservations._max_t)
    seen: Set[Tuple[int, str]] = set()
    open_heap: List[Tuple[int, int, int, str, List[Tuple[int, str]]]] = []
    g = 0
    h = _manhattan_heuristic(start, goal, zone_order)
    heapq.heappush(
        open_heap,
        (g + h, g, t0, start, [(t0, start)]),
    )

    while open_heap:
        _f, g, t, node, path = heapq.heappop(open_heap)
        if (t, node) in seen:
            continue
        seen.add((t, node))
        if node == goal:
            return path
        if t >= max_t:
            continue
        next_t = t + 1
        neighbors = graph.neighbors(node)
        if rng is not None:
            neighbors = sorted(neighbors)
            rng.shuffle(neighbors)
        for nbr in neighbors:
            if graph.is_restricted(node, nbr) and not has_restricted_token:
                continue
            occ = reservations.get(next_t, nbr)
            if occ is not None and occ != agent_id:
                continue
            if (next_t, nbr) in seen:
                continue
            new_path = path + [(next_t, nbr)]
            new_g = g + 1
            new_h = _manhattan_heuristic(nbr, goal, zone_order)
            heapq.heappush(
                open_heap,
                (new_g + new_h, new_g, next_t, nbr, new_path),
            )
        wait_node = node
        occ_wait = reservations.get(next_t, wait_node)
        if occ_wait is None or occ_wait == agent_id:
            if (next_t, wait_node) not in seen:
                new_path = path + [(next_t, wait_node)]
                heapq.heappush(
                    open_heap,
                    (
                        g + 1 + _manhattan_heuristic(wait_node, goal, zone_order),
                        g + 1,
                        next_t,
                        wait_node,
                        new_path,
                    ),
                )
    return []


def whca_route_and_reserve(
    agent_id: str,
    start: str,
    goal: str,
    t0: int,
    horizon: int,
    graph: RoutingGraph,
    reservations: ReservationTable,
    rng: Any,
    has_restricted_token: bool = False,
    zone_order: Optional[List[str]] = None,
) -> List[Tuple[int, str]]:
    """
    Plan with whca_route; if path found, reserve it and return path.
    Else return [].
    """
    path = whca_route(
        agent_id,
        start,
        goal,
        t0,
        horizon,
        graph,
        reservations,
        rng,
        has_restricted_token=has_restricted_token,
        zone_order=zone_order,
    )
    if path and reservations.reserve_path(path, agent_id):
        return path
    return []
