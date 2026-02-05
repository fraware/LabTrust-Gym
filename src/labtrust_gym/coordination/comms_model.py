"""
Comms model: delivers blackboard events to view replicas with configurable delay, drop, reorder, duplicate.

Deterministic: all randomness via seeded RNG.
Perfect mode: no delay/drop/reorder/duplicate (nominal baseline).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from labtrust_gym.coordination.blackboard import BlackboardEvent
from labtrust_gym.coordination.network import NetworkModel


@dataclass
class CommsConfig:
    """
    Configuration for CommsModel. All params used for deterministic behavior when seeded.
    perfect: if True, no delay/drop/reorder/duplicate (unless network_policy overrides).
    delay_ms_mean, delay_ms_max: delay distribution when network_policy is not set.
    drop_rate: probability each event is dropped (per agent) in (0, 1).
    reorder_window: max steps events can be reordered (0 = no reorder).
    duplicate_rate: probability an event is delivered twice (0, 1).
    network_policy: optional dict (network_policy.v0.1); when set, delivery routes through
        NetworkModel and delay/drop/reorder are taken from policy (deterministic, seeded).
    """

    perfect: bool = True
    delay_ms_mean: float = 0.0
    delay_ms_max: float = 0.0
    drop_rate: float = 0.0
    reorder_window: int = 0
    duplicate_rate: float = 0.0
    network_policy: Optional[Dict[str, Any]] = None


@dataclass
class Delivery:
    """One delivered event to one agent at a given delivery step and latency_ms."""

    agent_id: str
    event: BlackboardEvent
    delivery_step: int
    latency_ms: float


class CommsModel:
    """
    Delivers log events to agents with optional delay, drop, reorder, duplicate.
    apply(log_events, now_t) returns deliveries per agent (events to apply to each ViewReplica).
    Deterministic given seed.
    """

    __slots__ = (
        "_config",
        "_rng",
        "_agent_ids",
        "_pending_by_agent",
        "_msg_count",
        "_delivered_latencies_ms",
        "_dropped_count",
        "_network_model",
    )

    def __init__(
        self,
        agent_ids: List[str],
        config: Optional[CommsConfig] = None,
        seed: int = 0,
    ) -> None:
        self._config = config or CommsConfig()
        self._rng = random.Random(seed)
        self._agent_ids = sorted(agent_ids)
        self._pending_by_agent: Dict[str, List[Tuple[BlackboardEvent, int, float]]] = {
            aid: [] for aid in self._agent_ids
        }
        self._msg_count = 0
        self._delivered_latencies_ms: List[float] = []
        self._dropped_count = 0
        np = getattr(self._config, "network_policy", None)
        self._network_model: Optional[NetworkModel] = (
            NetworkModel(
                agent_ids=self._agent_ids,
                policy=np,
                rng=self._rng,
            )
            if np
            else None
        )

    def reset(self, seed: int) -> None:
        """Reset state and RNG for new episode."""
        self._rng = random.Random(seed)
        if self._network_model is not None:
            self._network_model.reset(self._rng)
        for aid in self._agent_ids:
            self._pending_by_agent[aid] = []
        self._msg_count = 0
        self._delivered_latencies_ms = []
        self._dropped_count = 0

    def apply(
        self,
        log_events: List[BlackboardEvent],
        now_t: int,
    ) -> Dict[str, List[BlackboardEvent]]:
        """
        Process new log events and current step; return deliveries per agent:
        { agent_id: [events to apply this step] }.
        When network_policy is set, routes through NetworkModel (delay/drop/partition/reorder).
        With perfect=True and no network_policy, all events are delivered immediately.
        Otherwise: delay, drop, reorder, duplicate are applied (seeded).
        """
        if self._network_model is not None:
            return self._network_model.apply(log_events, now_t)

        deliveries: Dict[str, List[BlackboardEvent]] = {
            aid: [] for aid in self._agent_ids
        }
        if not log_events:
            self._flush_pending(now_t, deliveries)
            return deliveries

        cfg = self._config
        if cfg.perfect:
            for ev in log_events:
                self._msg_count += len(self._agent_ids)
                self._delivered_latencies_ms.extend([0.0] * len(self._agent_ids))
                for aid in self._agent_ids:
                    deliveries[aid].append(ev)
            return deliveries

        # Non-perfect: per-agent delay/drop/duplicate; then reorder within window
        for ev in log_events:
            for aid in self._agent_ids:
                if self._rng.random() < cfg.drop_rate:
                    self._dropped_count += 1
                    continue
                delay_ms = min(
                    cfg.delay_ms_max,
                    max(0, self._rng.gauss(cfg.delay_ms_mean, cfg.delay_ms_mean * 0.5)),
                )
                delivery_step = now_t + int(delay_ms // 10)
                self._pending_by_agent[aid].append((ev, delivery_step, delay_ms))
                if self._rng.random() < cfg.duplicate_rate:
                    self._pending_by_agent[aid].append(
                        (ev, delivery_step + 1, delay_ms + 10.0)
                    )

        self._flush_pending(now_t, deliveries)
        return deliveries

    def _flush_pending(
        self,
        now_t: int,
        deliveries: Dict[str, List[BlackboardEvent]],
    ) -> None:
        """Move pending events that are due at now_t into deliveries; apply reorder_window."""
        cfg = self._config
        for aid in self._agent_ids:
            pending = self._pending_by_agent[aid]
            due = [(ev, step, lat) for ev, step, lat in pending if step <= now_t]
            self._pending_by_agent[aid] = [
                (ev, step, lat) for ev, step, lat in pending if step > now_t
            ]
            if not due:
                continue
            events_with_lat = sorted(due, key=lambda x: (x[1], x[0].id))
            if cfg.reorder_window > 0:
                events_with_lat = self._reorder(events_with_lat, cfg.reorder_window)
            for ev, _step, lat in events_with_lat:
                deliveries[aid].append(ev)
                self._msg_count += 1
                self._delivered_latencies_ms.append(lat)

    def _reorder(
        self,
        events_with_lat: List[Tuple[BlackboardEvent, int, float]],
        window: int,
    ) -> List[Tuple[BlackboardEvent, int, float]]:
        """Within window, randomly reorder (deterministic with self._rng)."""
        if window <= 0 or len(events_with_lat) <= 1:
            return events_with_lat
        out = list(events_with_lat)
        self._rng.shuffle(out)
        return out

    def get_metrics(self) -> Dict[str, Any]:
        """Return comm metrics for results: msg_count, p95_latency_ms, drop_rate, partition_events (if network)."""
        if self._network_model is not None:
            return self._network_model.get_metrics()
        n = len(self._delivered_latencies_ms)
        if n == 0:
            p95_ms = 0.0
        else:
            sorted_lat = sorted(self._delivered_latencies_ms)
            idx = min(int(0.95 * n), n - 1)
            p95_ms = sorted_lat[idx]
        total_attempts = self._msg_count + self._dropped_count
        drop_rate = self._dropped_count / total_attempts if total_attempts > 0 else 0.0
        return {
            "msg_count": self._msg_count,
            "p95_latency_ms": round(p95_ms, 2),
            "drop_rate": round(drop_rate, 4),
            "dropped_count": self._dropped_count,
        }
