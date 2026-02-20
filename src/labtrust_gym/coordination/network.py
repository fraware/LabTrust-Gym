"""
Network simulator for coordination messaging.

Models delay (p50/p95), packet drop, partition schedule, and reorder. All
randomness comes from a seeded RNG so behavior is reproducible. When a network
policy is provided, the SignedMessageBus (CommsModel) routes messages through
NetworkModel so that coordination methods can be tested under realistic delays
and failures.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from labtrust_gym.coordination.blackboard import BlackboardEvent


def _sample_delay_ms(rng: random.Random, p50_ms: float, p95_ms: float) -> float:
    """
    Sample latency (ms) from a lognormal-like distribution with given p50 and p95.
    Deterministic given rng state. If p50 <= 0 or p95 <= p50, returns 0.
    """
    if p50_ms <= 0 or p95_ms <= p50_ms:
        return 0.0
    mu = math.log(p50_ms)
    # 95th percentile of lognormal: exp(mu + 1.645*sigma) = p95 => sigma = (ln(p95)-mu)/1.645
    sigma = (math.log(p95_ms) - mu) / 1.645
    if sigma <= 0:
        return p50_ms
    return max(0.0, math.exp(rng.gauss(mu, sigma)))


def _resolve_partition_affected(
    partition_schedule: list[dict[str, Any]],
    agent_ids: list[str],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """
    Resolve affected_agent_fraction to affected_agents per interval (deterministic given rng).
    In-place style: returns new list with resolved intervals.
    """
    out: list[dict[str, Any]] = []
    for interval in partition_schedule or []:
        frac = interval.get("affected_agent_fraction")
        if frac is not None and isinstance(frac, int | float):
            k = max(0, min(len(agent_ids), int(len(agent_ids) * float(frac))))
            affected = set(rng.sample(agent_ids, k)) if k > 0 else set()
            out.append(
                {
                    "start_t": interval.get("start_t", 0),
                    "end_t": interval.get("end_t", 0),
                    "affected_agents": list(affected),
                }
            )
        else:
            out.append(
                {
                    "start_t": interval.get("start_t", 0),
                    "end_t": interval.get("end_t", 0),
                    "affected_agents": list(interval.get("affected_agents") or []),
                }
            )
    return out


def _is_partitioned(
    agent_id: str,
    now_t: int,
    partition_schedule: list[dict[str, Any]],
) -> bool:
    """True if agent is in a partition interval at now_t (no delivery)."""
    for interval in partition_schedule or []:
        start_t = interval.get("start_t", 0)
        end_t = interval.get("end_t", 0)
        if start_t <= now_t <= end_t:
            affected = interval.get("affected_agents") or []
            if agent_id in affected:
                return True
    return False


def _drop_rate_at_step(
    now_t: int,
    base_drop_rate: float,
    drop_spike: dict[str, Any] | None,
) -> float:
    """Effective drop rate at step now_t (spike overlay if in window)."""
    if drop_spike:
        s = drop_spike.get("start_t", 0)
        e = drop_spike.get("end_t", 0)
        if s <= now_t <= e:
            return float(drop_spike.get("drop_rate", base_drop_rate))
    return base_drop_rate


@dataclass
class NetworkModel:
    """
    Applies network effects to blackboard events: delay (p50/p95), drop, partition, reorder.
    apply(log_events, now_t) returns deliveries per agent. Deterministic given policy and rng.
    """

    __slots__ = (
        "_agent_ids",
        "_policy",
        "_resolved_partition",
        "_rng",
        "_pending_by_agent",
        "_msg_count",
        "_delivered_latencies_ms",
        "_dropped_count",
        "_partition_drop_count",
    )

    def __init__(
        self,
        agent_ids: list[str],
        policy: dict[str, Any],
        rng: random.Random,
    ) -> None:
        self._agent_ids = sorted(agent_ids)
        self._policy = policy or {}
        self._resolved_partition: list[dict[str, Any]] = []
        self._rng = rng
        self._pending_by_agent: dict[str, list[tuple[BlackboardEvent, int, float]]] = {
            aid: [] for aid in self._agent_ids
        }
        self._msg_count = 0
        self._delivered_latencies_ms: list[float] = []
        self._dropped_count = 0
        self._partition_drop_count = 0
        self._resolve_partition()

    def _resolve_partition(self) -> None:
        """Resolve affected_agent_fraction to affected_agents (deterministic from _rng)."""
        self._resolved_partition = _resolve_partition_affected(
            self._policy.get("partition_schedule") or [],
            self._agent_ids,
            self._rng,
        )

    def reset(self, rng: random.Random) -> None:
        """Reset state and RNG for new episode; re-resolve partition schedule."""
        self._rng = rng
        self._resolve_partition()
        for aid in self._agent_ids:
            self._pending_by_agent[aid] = []
        self._msg_count = 0
        self._delivered_latencies_ms = []
        self._dropped_count = 0
        self._partition_drop_count = 0

    def apply(
        self,
        log_events: list[BlackboardEvent],
        now_t: int,
    ) -> dict[str, list[BlackboardEvent]]:
        """
        Process new log events and current step; return deliveries per agent.
        Applies delay (p50/p95), drop_rate, partition_schedule, drop_spike, reorder_window.
        """
        deliveries: dict[str, list[BlackboardEvent]] = {aid: [] for aid in self._agent_ids}
        if not log_events:
            self._flush_pending(now_t, deliveries)
            return deliveries

        if self._policy.get("perfect", True):
            for ev in log_events:
                self._msg_count += len(self._agent_ids)
                self._delivered_latencies_ms.extend([0.0] * len(self._agent_ids))
                for aid in self._agent_ids:
                    deliveries[aid].append(ev)
            return deliveries

        delay_cfg = self._policy.get("delay") or {}
        p50_ms = float(delay_cfg.get("p50_ms", 10))
        p95_ms = float(delay_cfg.get("p95_ms", 50))
        base_drop = float(self._policy.get("drop_rate", 0.0))
        partition_schedule = self._resolved_partition
        drop_spike = self._policy.get("drop_spike")

        for ev in log_events:
            for aid in self._agent_ids:
                if _is_partitioned(aid, now_t, partition_schedule):
                    self._partition_drop_count += 1
                    continue
                drop_rate = _drop_rate_at_step(now_t, base_drop, drop_spike)
                if self._rng.random() < drop_rate:
                    self._dropped_count += 1
                    continue
                delay_ms = _sample_delay_ms(self._rng, p50_ms, p95_ms)
                # delivery_step: 1 step per 10ms (match CommsModel convention)
                delivery_step = now_t + max(0, int(delay_ms // 10))
                self._pending_by_agent[aid].append((ev, delivery_step, delay_ms))

        self._flush_pending(now_t, deliveries)
        return deliveries

    def _flush_pending(
        self,
        now_t: int,
        deliveries: dict[str, list[BlackboardEvent]],
    ) -> None:
        """Move pending events due at now_t into deliveries; apply reorder_window."""
        reorder_window = int(self._policy.get("reorder_window", 0))
        for aid in self._agent_ids:
            pending = self._pending_by_agent[aid]
            due = [(ev, step, lat) for ev, step, lat in pending if step <= now_t]
            self._pending_by_agent[aid] = [(ev, step, lat) for ev, step, lat in pending if step > now_t]
            if not due:
                continue
            events_with_lat = sorted(due, key=lambda x: (x[1], x[0].id))
            if reorder_window > 0:
                events_with_lat = self._reorder(events_with_lat, reorder_window)
            for ev, _step, lat in events_with_lat:
                deliveries[aid].append(ev)
                self._msg_count += 1
                self._delivered_latencies_ms.append(lat)

    def _reorder(
        self,
        events_with_lat: list[tuple[BlackboardEvent, int, float]],
        window: int,
    ) -> list[tuple[BlackboardEvent, int, float]]:
        """Within-window random reorder (deterministic with self._rng)."""
        if window <= 0 or len(events_with_lat) <= 1:
            return events_with_lat
        out = list(events_with_lat)
        self._rng.shuffle(out)
        return out

    def get_metrics(self) -> dict[str, Any]:
        """Return comm metrics: msg_count, p95_latency_ms, drop_rate, partition_events."""
        n = len(self._delivered_latencies_ms)
        if n == 0:
            p95_ms = 0.0
        else:
            sorted_lat = sorted(self._delivered_latencies_ms)
            idx = min(int(0.95 * n), n - 1)
            p95_ms = sorted_lat[idx]
        total_attempts = self._msg_count + self._dropped_count + self._partition_drop_count
        drop_rate = (self._dropped_count + self._partition_drop_count) / total_attempts if total_attempts > 0 else 0.0
        return {
            "msg_count": self._msg_count,
            "p95_latency_ms": round(p95_ms, 2),
            "drop_rate": round(drop_rate, 4),
            "dropped_count": self._dropped_count,
            "partition_events": self._partition_drop_count,
        }
