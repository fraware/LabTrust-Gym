"""
Tests for bundle bidding: bundle_id_same_zone, run_bundle_auction_greedy.
"""

from __future__ import annotations

import random

from labtrust_gym.baselines.coordination.allocation.auction import WorkItem
from labtrust_gym.baselines.coordination.allocation.bundle_bidding import (
    bundle_id_same_zone,
    run_bundle_auction_greedy,
)


def test_bundle_id_same_zone() -> None:
    """Items in same zone form one bundle."""
    items = [
        WorkItem("W1", "D1", "Z_A", 1),
        WorkItem("W2", "D2", "Z_A", 0),
        WorkItem("W3", "D1", "Z_B", 2),
    ]
    bundles = bundle_id_same_zone(items)
    assert len(bundles) == 2
    assert "Z_A" in bundles and "Z_B" in bundles


def test_run_bundle_auction_greedy() -> None:
    """One agent wins bundle; assignments returned."""
    items = [
        WorkItem("W1", "D1", "Z_A", 1),
        WorkItem("W2", "D2", "Z_A", 0),
    ]
    rng = random.Random(42)

    def bid_fn(agent: str, bundle: frozenset, work_so_far: dict) -> float:
        return 1.0 if agent == "a1" else 10.0

    out = run_bundle_auction_greedy(items, ["a1", "a2"], bid_fn, 10, rng)
    assert len(out) == 2
    assert all(a[0] == "a1" for a in out)


def test_bundle_wins_vs_two_bids_a1_near() -> None:
    """Two tasks in same zone; a1 (near) has lower bundle cost than a2 (far); a1 wins the bundle."""
    items = [
        WorkItem("W1", "D1", "Z_A", 1),
        WorkItem("W2", "D2", "Z_A", 0),
    ]
    rng = random.Random(42)

    def bid_fn(agent: str, bundle: frozenset, work_so_far: dict) -> float:
        if agent == "a1":
            return 2.0
        return 100.0

    out = run_bundle_auction_greedy(items, ["a1", "a2"], bid_fn, 10, rng)
    assert len(out) == 2
    assert all(a[0] == "a1" for a in out)
    assert {(a[1], a[2]) for a in out} == {("W1", "D1"), ("W2", "D2")}


def test_bundle_wins_both_when_bundle_cheaper_than_split() -> None:
    """Bundle bid: a1 bids low for whole bundle, a2 high; both tasks go to a1.
    Separate bids per task could assign W1->a1, W2->a2; bundle assigns both to a1."""
    items = [
        WorkItem("W1", "D1", "Z_A", 0),
        WorkItem("W2", "D2", "Z_A", 0),
    ]
    rng = random.Random(43)

    def bid_fn(agent: str, bundle: frozenset, work_so_far: dict) -> float:
        if agent == "a1":
            return 3.0
        return 5.0

    out = run_bundle_auction_greedy(items, ["a1", "a2"], bid_fn, 10, rng)
    assert len(out) == 2
    assert all(a[0] == "a1" for a in out)
