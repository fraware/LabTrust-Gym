"""
Coordination-layer routing invariants (study runner or tests).
Not engine invariants; they apply to planned routes over the horizon.

INV-ROUTE-001: no same-node same-time (current semantics). Optional invariant_id
in telemetry/evidence: used in simplex assurance_evidence and in runner
invariants_considered when shield is applied. Same-edge-at-same-time is covered
indirectly via swap (INV-ROUTE-SWAP) for typical graphs; extend to explicit
same-edge check only if needed for richer graphs.
Invariant IDs INV_ROUTE_001, INV_ROUTE_002, INV_ROUTE_SWAP are the single source of truth. INV-ROUTE-004
reserved for future use (e.g. multi-step move rules) if introduced.
"""

from __future__ import annotations

INV_ROUTE_001 = "INV-ROUTE-001"
INV_ROUTE_002 = "INV-ROUTE-002"


def check_inv_route_001(planned: list[tuple[str, int, str]]) -> list[str]:
    """
    INV-ROUTE-001: No two agents occupy same node at same time over planned horizon.
    planned: list of (agent_id, t, node_id).
    Returns list of violation descriptions (empty if satisfied).
    """
    occupied: dict[tuple[int, str], str] = {}
    violations: list[str] = []
    for agent_id, t, node in planned:
        key = (t, node)
        if key in occupied and occupied[key] != agent_id:
            violations.append(f"{INV_ROUTE_001}: (t={t}, node={node}) occupied by {occupied[key]} and {agent_id}")
        occupied[key] = agent_id
    return violations


def check_inv_route_002(
    planned_moves: list[tuple[str, int, str, str]],
    restricted_edges: set[tuple[str, str]],
    agent_has_token: dict[str, bool],
) -> list[str]:
    """
    INV-ROUTE-002: Restricted door edges require valid token or are never planned.
    planned_moves: (agent_id, t, from_node, to_node).
    restricted_edges: set of (from, to) that require token.
    agent_has_token: agent_id -> has_restricted_token.
    Returns list of violation descriptions.
    """
    violations: list[str] = []
    for agent_id, t, from_n, to_n in planned_moves:
        edge = (from_n, to_n)
        if edge not in restricted_edges and (to_n, from_n) not in restricted_edges:
            continue
        if not agent_has_token.get(agent_id, False):
            violations.append(
                f"{INV_ROUTE_002}: {agent_id} planned restricted edge ({from_n},{to_n}) at t={t} without token"
            )
    return violations


INV_ROUTE_SWAP = "INV-ROUTE-SWAP"


def check_swap_collision(
    planned_moves: list[tuple[str, int, str, str]],
) -> list[str]:
    """
    INV-ROUTE-SWAP (swap-collision invariant): No A->B and B->A at same time t.
    planned_moves: (agent_id, t, from_node, to_node).
    Returns list of violation descriptions (empty if satisfied).
    """
    by_t: dict[int, list[tuple[str, str, str]]] = {}
    for agent_id, t, from_n, to_n in planned_moves:
        by_t.setdefault(t, []).append((agent_id, from_n, to_n))
    violations: list[str] = []
    for t, moves in by_t.items():
        for i, (a_id, a_from, a_to) in enumerate(moves):
            for b_id, b_from, b_to in moves[i + 1 :]:
                if (a_from, a_to) == (b_to, b_from):
                    violations.append(
                        f"{INV_ROUTE_SWAP}: swap collision at t={t}: {a_id} {a_from}->{a_to} "
                        f"and {b_id} {b_from}->{b_to}"
                    )
    return violations
