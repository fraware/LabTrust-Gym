"""
Hierarchical coordination: HubPlanner (macro per region/site) and LocalControllers (EDF + WHCA per region).
Deterministic region partition; handoff protocol for cross-region work.
"""

from labtrust_gym.baselines.coordination.hierarchical.region_partition import (
    partition_zones_into_regions,
    zone_to_region_map,
)
from labtrust_gym.baselines.coordination.hierarchical.hub_planner import (
    HubPlanner,
    MacroAssignment,
)
from labtrust_gym.baselines.coordination.hierarchical.local_controller import (
    LocalController,
)
from labtrust_gym.baselines.coordination.hierarchical.handoff import (
    HandoffEvent,
    HandoffProtocol,
    HUB_REGION_ID,
)
from labtrust_gym.baselines.coordination.hierarchical.hierarchical_method import (
    HierarchicalHubLocal,
)

__all__ = [
    "partition_zones_into_regions",
    "zone_to_region_map",
    "HubPlanner",
    "MacroAssignment",
    "LocalController",
    "HandoffEvent",
    "HandoffProtocol",
    "HUB_REGION_ID",
    "HierarchicalHubLocal",
]
