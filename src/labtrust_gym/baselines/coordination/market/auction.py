"""
Deterministic auction engine: input typed bids and constraints, output assignments.
Strict bid validation (ranges, units, no NaN/Inf). Metrics: bid_skew,
gini_work_distribution, collusion_suspected_proxy (heuristic).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

ALLOWED_BID_UNITS = ("cost", "time")
MIN_BID_VALUE = 0.0
MAX_BID_VALUE = 1e6


@dataclass
class WorkItem:
    """One work item (queue head) to assign."""

    work_id: str
    device_id: str
    zone_id: str
    priority: int  # 2=STAT, 1=URGENT, 0=ROUTINE

    def bundle_id(self) -> str:
        return f"{self.device_id}:{self.work_id}"


@dataclass
class TypedBid:
    """
    Single bid: agent, bundle, value, units, optional constraints.
    Optional explainable decomposition (Phase 5): travel_time_estimate,
    queue_delay_estimate, risk_penalty, fairness_penalty for recompute validation.
    """

    agent_id: str
    bundle_id: str
    value: float
    units: str = "cost"
    constraints: dict[str, Any] = field(default_factory=dict)
    travel_time_estimate: float | None = None
    queue_delay_estimate: float | None = None
    risk_penalty: float | None = None
    fairness_penalty: float | None = None


def validate_bid(
    value: Any,
    units: Any,
    *,
    constraints: dict[str, Any] | None = None,
    min_value: float = MIN_BID_VALUE,
    max_value: float = MAX_BID_VALUE,
) -> tuple[bool, str]:
    """
    Strict validation for a single bid. Returns (valid, error_message).
    - value: finite number in [min_value, max_value], no NaN/Inf.
    - units: must be in ALLOWED_BID_UNITS.
    - constraints: must be dict (no validation of contents beyond type).
    """
    if constraints is None:
        constraints = {}
    if not isinstance(constraints, dict):
        return False, "constraints must be object"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False, "bid value must be numeric"
    if math.isnan(v) or math.isinf(v):
        return False, "bid value must be finite (no NaN/Inf)"
    if v < min_value or v > max_value:
        return False, f"bid value must be in [{min_value}, {max_value}]"
    u = str(units).strip().lower() if units is not None else "cost"
    if u not in ALLOWED_BID_UNITS:
        return False, f"bid units must be one of {ALLOWED_BID_UNITS}"
    return True, ""


def gini_work_distribution(work_per_agent: dict[str, int]) -> float:
    """
    Gini coefficient for work distribution (0 = equal, 1 = maximally unequal).
    Deterministic.
    """
    if not work_per_agent:
        return 0.0
    counts = sorted(work_per_agent.values())
    n = len(counts)
    if n == 0:
        return 0.0
    cumul = 0.0
    for i, v in enumerate(counts):
        cumul += (2 * (i + 1) - n - 1) * v
    total = sum(counts)
    if total == 0:
        return 0.0
    return float(cumul) / (n * total)


def collusion_suspected_proxy(
    bids_used: list[tuple[str, str, float]],
    assignments: list[tuple[str, str, str, int]],
    *,
    win_share_threshold: float = 0.5,
    low_variance_threshold: float = 0.1,
) -> tuple[bool, dict[str, Any]]:
    """
    Simple heuristic for collusion suspicion. Returns (suspected, details).
    - One agent wins > win_share_threshold of assignments.
    - Or winning-bid variance (normalized) very low (suspiciously similar).
    """
    details: dict[str, Any] = {
        "win_share_max": 0.0,
        "dominant_agent": None,
        "bid_cv": 0.0,
        "suspicion_reason": "",
    }
    if not bids_used or not assignments:
        return False, details
    bids_only = [b[2] for b in bids_used]
    n = len(bids_only)
    mean_bid = sum(bids_only) / n
    variance = sum((x - mean_bid) ** 2 for x in bids_only) / n
    std = math.sqrt(variance) if variance > 0 else 0.0
    cv = (std / mean_bid) if mean_bid > 0 else 0.0
    details["bid_cv"] = round(cv, 4)
    wins_per_agent: dict[str, int] = {}
    for agent_id, _work_id, _dev_id, _prio in assignments:
        wins_per_agent[agent_id] = wins_per_agent.get(agent_id, 0) + 1
    total_wins = len(assignments)
    if total_wins == 0:
        return False, details
    for agent_id, _work_id, _bid in bids_used:
        share = wins_per_agent.get(agent_id, 0) / total_wins
        if share > details["win_share_max"]:
            details["win_share_max"] = round(share, 4)
            details["dominant_agent"] = agent_id
    if details["win_share_max"] >= win_share_threshold:
        details["suspicion_reason"] = "high_win_share"
        return True, details
    if cv <= low_variance_threshold and n >= 2:
        details["suspicion_reason"] = "low_bid_variance"
        return True, details
    return False, details


def clear_auction(
    work_items: list[WorkItem],
    bids: list[TypedBid],
    rng: Any,
    *,
    max_assignments: int | None = None,
) -> tuple[
    list[tuple[str, str, str, int]],
    list[tuple[str, str, float]],
    dict[str, Any],
]:
    """
    Deterministic auction: assign each work item to lowest valid bidder.
    Returns (assignments, bids_used, metrics).
    assignments: (agent_id, work_id, device_id, priority)
    bids_used: (agent_id, work_id, bid_value)
    metrics: gini_work_distribution, bid_skew (cv of winning bids), mean_bid,
    num_assignments, collusion_suspected, collusion_details.
    """
    sorted_items = sorted(
        work_items,
        key=lambda x: (-x.priority, x.device_id, x.work_id),
    )
    assignments: list[tuple[str, str, str, int]] = []
    bids_used: list[tuple[str, str, float]] = []
    assigned_agents: set[str] = set()
    used_bundles: set[str] = set()
    cap = max_assignments if max_assignments is not None else len(work_items) * 2

    for item in sorted_items:
        if len(assignments) >= cap:
            break
        bid = item.bundle_id()
        if bid in used_bundles:
            continue
        candidate_bids: list[tuple[float, str, int]] = []
        for b in bids:
            if b.bundle_id != bid:
                continue
            if b.agent_id in assigned_agents:
                continue
            ok, _ = validate_bid(b.value, b.units, constraints=b.constraints)
            if not ok:
                continue
            tie = rng.randint(0, 999) if rng else 0
            candidate_bids.append((b.value, b.agent_id, tie))
        if not candidate_bids:
            continue
        candidate_bids.sort(key=lambda x: (x[0], x[2], x[1]))
        best_val, winner, _ = candidate_bids[0]
        assigned_agents.add(winner)
        used_bundles.add(bid)
        assignments.append((winner, item.work_id, item.device_id, item.priority))
        bids_used.append((winner, item.work_id, best_val))

    work_per_agent: dict[str, int] = {}
    for agent_id, _w, _d, _p in assignments:
        work_per_agent[agent_id] = work_per_agent.get(agent_id, 0) + 1
    gini = gini_work_distribution(work_per_agent)
    bid_values = [b[2] for b in bids_used]
    mean_bid = sum(bid_values) / len(bid_values) if bid_values else 0.0
    variance = sum((x - mean_bid) ** 2 for x in bid_values) / len(bid_values) if bid_values else 0.0
    std = math.sqrt(variance) if variance > 0 else 0.0
    bid_skew = (std / mean_bid) if mean_bid > 0 else 0.0
    collusion, collusion_details = collusion_suspected_proxy(
        bids_used,
        assignments,
    )
    metrics: dict[str, Any] = {
        "gini_work_distribution": round(gini, 4),
        "bid_skew": round(bid_skew, 4),
        "mean_bid": round(mean_bid, 4),
        "num_assignments": len(assignments),
        "collusion_suspected_proxy": collusion,
        "collusion_details": collusion_details,
    }
    return assignments, bids_used, metrics
