"""
Tests for CRDT-style merges and Byzantine aggregation.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.crdt_merges import (
    byzantine_aggregate,
    lww_register_merge,
    or_set_merge,
    pn_counter_merge,
)


def test_lww_register_merge() -> None:
    """LWW: higher (epoch, clock) wins."""
    assert lww_register_merge((1, 0, "a"), (2, 0, "b")) == (2, 0, "b")
    assert lww_register_merge((2, 1, "b"), (1, 0, "a")) == (2, 1, "b")


def test_pn_counter_merge() -> None:
    """PN-counter: per-key max."""
    assert pn_counter_merge({"z": 2}, {"z": 3}) == {"z": 3}


def test_or_set_merge() -> None:
    """OR-set: union adds/tombstones; result = adds - tombstones."""
    adds, tomb = or_set_merge({"x"}, {"y"}, {"z"}, set())
    assert adds == {"x", "z"} - tomb


def test_byzantine_aggregate_trim_mean() -> None:
    """Trim k smallest/largest then mean."""
    v = [1.0, 2.0, 3.0, 4.0, 5.0, 100.0]
    out = byzantine_aggregate(v, k=1, method="trim_mean")
    assert 3.0 <= out <= 5.0


def test_crdt_merge_order_independence() -> None:
    """Merge (A then B) and (B then A) yield same final state."""
    a_pn = {"z1": 2, "z2": 1}
    b_pn = {"z1": 1, "z2": 3}
    ab = pn_counter_merge(pn_counter_merge({}, a_pn), b_pn)
    ba = pn_counter_merge(pn_counter_merge({}, b_pn), a_pn)
    assert ab == ba
    assert ab == {"z1": 2, "z2": 3}

    a_lww = (1, 0, "a")
    b_lww = (2, 1, "b")
    ab_lww = lww_register_merge(lww_register_merge((0, 0, None), a_lww), b_lww)
    ba_lww = lww_register_merge(lww_register_merge((0, 0, None), b_lww), a_lww)
    assert ab_lww == ba_lww
    assert ab_lww == (2, 1, "b")


def test_byzantine_inject_k_trim_mean() -> None:
    """Inject k Byzantine values; trim_mean returns value in reasonable range."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    poisoned = values + [1000.0]
    out = byzantine_aggregate(poisoned, k=1, method="trim_mean")
    assert 2.0 <= out <= 5.0
    poisoned2 = values + [1000.0, 999.0]
    out2 = byzantine_aggregate(poisoned2, k=2, method="trim_mean")
    assert 2.0 <= out2 <= 5.0


def test_byzantine_inject_k_graceful_degradation() -> None:
    """With k Byzantine agents, aggregate degrades gracefully (k=0 vs k=1 vs k=2)."""
    honest = [10.0, 11.0, 12.0, 13.0, 14.0]
    out0 = byzantine_aggregate(honest, k=0, method="trim_mean")
    out1 = byzantine_aggregate(honest + [1000.0], k=1, method="trim_mean")
    out2 = byzantine_aggregate(honest + [1000.0, 999.0], k=2, method="trim_mean")
    assert abs(out0 - 12.0) < 1.0
    assert abs(out1 - 12.0) < 3.0
    assert abs(out2 - 12.0) < 3.0
    assert out0 <= out1 + 5.0 and out0 <= out2 + 5.0
