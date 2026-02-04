"""
Coordination-layer routing invariants (evaluated in study runner or tests).
Not engine invariants; they apply to planned routes over the horizon.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

INV_ROUTE_001 = "INV-ROUTE-001"
INV_ROUTE_002 = "INV-ROUTE-002"


def check_inv_route_001(planned: List[Tuple[str, int, str]]) -> List[str]:
    """
    INV-ROUTE-001: No two agents occupy same node at same time over planned horizon.
    planned: list of (agent_id, t, node_id).
    Returns list of violation descriptions (empty if satisfied).
    """
    occupied: Dict[Tuple[int, str], str] = {}
    violations: List[str] = []
    for agent_id, t, node in planned:
        key = (t, node)
        if key in occupied and occupied[key] != agent_id:
            violations.append(
                f"{INV_ROUTE_001}: (t={t}, node={node}) "
                f"occupied by {occupied[key]} and {agent_id}"
            )
        occupied[key] = agent_id
    return violations


def check_inv_route_002(
    planned_moves: List[Tuple[str, int, str, str]],
    restricted_edges: Set[Tuple[str, str]],
    agent_has_token: Dict[str, bool],
) -> List[str]:
    """
    INV-ROUTE-002: Restricted door edges require valid token or are never planned.
    planned_moves: (agent_id, t, from_node, to_node).
    restricted_edges: set of (from, to) that require token.
    agent_has_token: agent_id -> has_restricted_token.
    Returns list of violation descriptions.
    """
    violations: List[str] = []
    for agent_id, t, from_n, to_n in planned_moves:
        edge = (from_n, to_n)
        if edge not in restricted_edges and (to_n, from_n) not in restricted_edges:
            continue
        if not agent_has_token.get(agent_id, False):
            violations.append(
                f"{INV_ROUTE_002}: {agent_id} planned restricted edge "
                f"({from_n},{to_n}) at t={t} without token"
            )
    return violations
