"""
Routing graph from zone_layout: zones as nodes, graph_edges as edges.
Restricted edges (via doors requiring token) are marked for INV-ROUTE-002.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from labtrust_gym.engine.zones import (
    build_adjacency_set,
    build_doors_map,
)


class RoutingGraph:
    """
    Topological graph for routing: nodes = zone_ids, edges from zone_layout graph_edges.
    Restricted edges (door requiring token) must not be planned without valid token.
    Node capacity default 1 (one agent per zone per time step).
    """

    __slots__ = (
        "_nodes",
        "_neighbors",
        "_restricted_edges",
        "_capacity",
    )

    def __init__(
        self,
        nodes: Set[str],
        edges: Set[Tuple[str, str]],
        restricted_edges: Optional[Set[Tuple[str, str]]] = None,
        capacity: Optional[Dict[str, int]] = None,
    ) -> None:
        self._nodes = set(nodes)
        self._neighbors: Dict[str, List[str]] = {}
        for a, b in edges:
            if a in self._nodes and b in self._nodes:
                self._neighbors.setdefault(a, []).append(b)
                self._neighbors.setdefault(b, []).append(a)
        for n in self._nodes:
            if n not in self._neighbors:
                self._neighbors[n] = []
        for k in self._neighbors:
            self._neighbors[k] = sorted(set(self._neighbors[k]))
        self._restricted_edges = set(restricted_edges or [])
        self._capacity = dict(capacity or {})
        for n in self._nodes:
            if n not in self._capacity:
                self._capacity[n] = 1

    def nodes(self) -> Set[str]:
        return set(self._nodes)

    def neighbors(self, node: str) -> List[str]:
        return list(self._neighbors.get(node, []))

    def is_restricted(self, from_node: str, to_node: str) -> bool:
        return (from_node, to_node) in self._restricted_edges or (
            to_node,
            from_node,
        ) in self._restricted_edges

    def capacity(self, node: str) -> int:
        return self._capacity.get(node, 1)

    @property
    def restricted_edges_set(self) -> Set[Tuple[str, str]]:
        """Set of (from, to) edges that require token (for shield validation)."""
        return set(self._restricted_edges)


def build_routing_graph(layout: Dict[str, Any]) -> RoutingGraph:
    """
    Build RoutingGraph from zone_layout policy dict (zones, doors, graph_edges).
    Zones from layout["zones"]; edges from graph_edges; restricted edges from
    doors with requires_token (via_door in graph_edges).
    Accepts layout or layout["zone_layout_policy"].
    """
    if not layout:
        raise ValueError("layout is empty")
    inner = layout.get("zone_layout_policy") or layout
    zones_list = inner.get("zones") or []
    nodes: Set[str] = set()
    for z in zones_list:
        if isinstance(z, dict) and z.get("zone_id"):
            nodes.add(str(z["zone_id"]))
    graph_edges = inner.get("graph_edges") or []
    doors_list = inner.get("doors") or []
    doors_map = build_doors_map(doors_list)
    edge_to_door: Dict[Tuple[str, str], str] = {}
    for e in graph_edges:
        f, t = e.get("from"), e.get("to")
        if f and t:
            via = e.get("via_door")
            if via:
                edge_to_door[(str(f), str(t))] = str(via)
                edge_to_door[(str(t), str(f))] = str(via)
    adj = build_adjacency_set(graph_edges)
    restricted_edges: Set[Tuple[str, str]] = set()
    for (a, b), door_id in edge_to_door.items():
        d = doors_map.get(door_id)
        if d and (d.get("restricted") or d.get("requires_token")):
            restricted_edges.add((a, b))
    for n in list(adj):
        a, b = n
        nodes.add(a)
        nodes.add(b)
    return RoutingGraph(
        nodes=nodes,
        edges=adj,
        restricted_edges=restricted_edges,
    )
