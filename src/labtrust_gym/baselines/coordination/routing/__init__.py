"""
WHCA*-style reservation routing over zone graph.

Graph from zone_layout; reservation table for collision-free plans;
windowed cooperative A* with deadlock-safe fallback.
"""

from labtrust_gym.baselines.coordination.routing.fallback import (
    priority_aging,
    safe_wait_policy,
)
from labtrust_gym.baselines.coordination.routing.graph import (
    RoutingGraph,
    build_routing_graph,
)
from labtrust_gym.baselines.coordination.routing.invariants import (
    INV_ROUTE_001,
    INV_ROUTE_002,
    INV_ROUTE_SWAP,
    check_inv_route_001,
    check_inv_route_002,
    check_swap_collision,
)
from labtrust_gym.baselines.coordination.routing.reservations import (
    ReservationTable,
)
from labtrust_gym.baselines.coordination.routing.whca_router import (
    whca_route,
)

__all__ = [
    "RoutingGraph",
    "build_routing_graph",
    "ReservationTable",
    "whca_route",
    "safe_wait_policy",
    "priority_aging",
    "INV_ROUTE_001",
    "INV_ROUTE_002",
    "INV_ROUTE_SWAP",
    "check_inv_route_001",
    "check_inv_route_002",
    "check_swap_collision",
]
