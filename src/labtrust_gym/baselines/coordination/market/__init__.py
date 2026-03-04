"""
Market-based coordination: typed bids, deterministic auction, dispatcher.
"""

from labtrust_gym.baselines.coordination.market.auction import (
    TypedBid,
    WorkItem,
    clear_auction,
    collusion_suspected_proxy,
    gini_work_distribution,
    validate_bid,
)

__all__ = [
    "clear_auction",
    "validate_bid",
    "WorkItem",
    "TypedBid",
    "gini_work_distribution",
    "collusion_suspected_proxy",
]
