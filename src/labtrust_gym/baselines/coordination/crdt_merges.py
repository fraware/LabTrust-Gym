"""
CRDT-style state merges for gossip/consensus: LWW register, PN-counter, OR-set.
Merge order independence; duplicate delivery idempotence; partition/rejoin.
"""

from __future__ import annotations

from typing import Any


def lww_register_merge(
    current: tuple[int, int, Any],
    incoming: tuple[int, int, Any],
) -> tuple[int, int, Any]:
    """LWW: (epoch, logical_clock, value). Higher (epoch, clock) wins."""
    if not incoming or (current and current[:2] >= incoming[:2]):
        return current
    return incoming


def pn_counter_merge(
    current: dict[str, int],
    incoming: dict[str, int],
) -> dict[str, int]:
    """PN-counter: per-key max of counts. Idempotent."""
    out = dict(current)
    for k, v in (incoming or {}).items():
        out[k] = max(out.get(k, 0), v)
    return out


def or_set_merge(
    current: set[str],
    tombstones: set[str],
    incoming: set[str],
    incoming_tombstones: set[str],
) -> tuple[set[str], set[str]]:
    """OR-set with tombstones: union adds/tombstones; result = adds - tombstones."""
    adds = (current or set()) | (incoming or set())
    tomb = (tombstones or set()) | (incoming_tombstones or set())
    return (adds - tomb, tomb)


def byzantine_aggregate(
    values: list[float],
    k: int,
    method: str = "trim_mean",
) -> float:
    """
    Aggregate with up to k Byzantine: trim k smallest/largest, then mean/median.
    """
    if not values or k < 0:
        return 0.0
    n = len(values)
    if n <= 2 * k:
        return float(sum(values)) / n
    sorted_v = sorted(values)
    trimmed = sorted_v[k : n - k]
    if method == "median":
        mid = len(trimmed) // 2
        return (trimmed[mid] + trimmed[-1 - mid]) / 2.0
    return float(sum(trimmed)) / len(trimmed)
