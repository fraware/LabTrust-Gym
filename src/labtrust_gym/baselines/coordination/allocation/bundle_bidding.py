"""
Bundle bidding: bids target a bundle_id (set of tasks, same zone or device chain).
Clearing: greedy within budget. Deterministic tie-breaks.
"""

from __future__ import annotations

from typing import Any, Callable

from labtrust_gym.baselines.coordination.allocation.auction import WorkItem


def bundle_id_same_zone(items: list[WorkItem]) -> dict[str, frozenset[tuple[str, str]]]:
    """Group items by zone_id; each zone yields one bundle_id."""
    by_zone: dict[str, list[tuple[str, str]]] = {}
    for w in items:
        key = (w.device_id, w.work_id)
        by_zone.setdefault(w.zone_id, []).append(key)
    return {zone: frozenset(pairs) for zone, pairs in by_zone.items()}


def run_bundle_auction_greedy(
    items: list[WorkItem],
    agents: list[str],
    bid_fn: Callable[[str, frozenset[tuple[str, str]], Any], float],
    max_assignments: int,
    rng: Any,
) -> list[tuple[str, str, str, int]]:
    """Greedy bundle clearing; returns assignments."""
    bundles = bundle_id_same_zone(items)
    item_lookup = {(w.device_id, w.work_id): w for w in items}
    assignments: list[tuple[str, str, str, int]] = []
    work_so_far: dict[str, int] = {a: 0 for a in agents}
    for zone, bundle in sorted(bundles.items()):
        if len(assignments) >= max_assignments:
            break
        best_agent: str | None = None
        best_bid = float("inf")
        for a in sorted(agents):
            bid = bid_fn(a, bundle, work_so_far)
            if bid < best_bid:
                best_bid = bid
                best_agent = a
        if best_agent is None or best_bid >= 1e9:
            continue
        for (dev_id, work_id) in bundle:
            w = item_lookup.get((dev_id, work_id))
            if w is not None:
                assignments.append((best_agent, work_id, dev_id, w.priority))
        work_so_far[best_agent] = work_so_far.get(best_agent, 0) + len(bundle)
    return assignments[:max_assignments]
