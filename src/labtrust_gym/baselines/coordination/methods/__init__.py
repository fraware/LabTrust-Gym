"""Coordination method implementations."""

from labtrust_gym.baselines.coordination.methods.centralized_planner import (
    CentralizedPlanner,
)
from labtrust_gym.baselines.coordination.methods.gossip_consensus import (
    GossipConsensus,
)
from labtrust_gym.baselines.coordination.methods.hierarchical_hub_rr import (
    HierarchicalHubRR,
)
from labtrust_gym.baselines.coordination.methods.llm_constrained import (
    LLMConstrained,
)
from labtrust_gym.baselines.coordination.methods.market_auction import (
    MarketAuction,
)
from labtrust_gym.baselines.coordination.methods.swarm_reactive import (
    SwarmReactive,
)

__all__ = [
    "CentralizedPlanner",
    "GossipConsensus",
    "HierarchicalHubRR",
    "LLMConstrained",
    "MarketAuction",
    "SwarmReactive",
]

# marl_ppo: optional import in registry only (requires [marl])
try:
    from labtrust_gym.baselines.coordination.methods.marl_ppo import (
        MarlPPOCoordination,
        make_marl_ppo_if_available,
    )

    __all__.extend(["MarlPPOCoordination", "make_marl_ppo_if_available"])
except ImportError:
    MarlPPOCoordination = None  # type: ignore[misc, assignment]
    make_marl_ppo_if_available = None  # type: ignore[misc, assignment]
