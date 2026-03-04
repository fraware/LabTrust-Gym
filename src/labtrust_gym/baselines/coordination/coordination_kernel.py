"""
Coordination kernel: separation of ALLOCATION, SCHEDULING, and ROUTING.

KernelContext provides a state snapshot, policy, scale config, time, and seeded RNG.
Allocator, Scheduler, and Router are protocols; composition yields a CoordinationMethod.
Deterministic: every tie-break must use context.rng.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Protocol, runtime_checkable

from labtrust_gym.baselines.coordination.decision_types import (
    AllocationDecision,
    RouteDecision,
    ScheduleDecision,
)


def _to_json_safe(obj: Any) -> Any:
    """Recursively convert numpy arrays/scalars and nested structures to JSON-serializable form."""
    try:
        import numpy as np

        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.floating, np.integer, np.bool_, np.str_, np.bytes_)):
            return obj.item()
        if hasattr(obj, "tolist") and callable(obj.tolist):
            return obj.tolist()
        if hasattr(obj, "item") and callable(obj.item):
            return obj.item()
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(x) for x in obj]
    return obj


def _stable_hash(obj: Any) -> str:
    """Deterministic SHA-256 hash of obj (converts numpy types to JSON-serializable first)."""
    obj_safe = _to_json_safe(obj)
    try:
        payload = json.dumps(obj_safe, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        payload = str(type(obj).__name__) + str(id(obj))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class KernelContext:
    """
    State snapshot and parameters for one coordination step.
    Deterministic: same inputs and seed => same rng sequence.
    """

    __slots__ = (
        "obs",
        "infos",
        "t",
        "policy",
        "scale_config",
        "seed",
        "rng",
        "agent_ids",
        "zone_ids",
        "device_ids",
        "device_zone",
        "adjacency",
        "_state_hash",
        "global_log",
        "view_snapshots",
    )

    def __init__(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
        seed: int,
        rng: random.Random | None = None,
        global_log: Any | None = None,
        view_snapshots: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.obs = obs
        self.infos = infos
        self.t = t
        self.policy = policy
        self.scale_config = scale_config
        self.seed = seed
        self.rng = rng or random.Random(seed + t)
        self.agent_ids = sorted(obs.keys()) if obs else []
        self.zone_ids = self._extract_zone_ids()
        self.device_ids = self._extract_device_ids()
        self.device_zone = self._extract_device_zone()
        self.adjacency = self._extract_adjacency()
        self._state_hash = ""
        self.global_log = global_log
        self.view_snapshots = view_snapshots or {}

    def _extract_zone_ids(self) -> list[str]:
        layout = (self.policy or {}).get("zone_layout") or {}
        zones = layout.get("zones") or []
        if isinstance(zones, list):
            return [str(z.get("zone_id", "")) for z in zones if isinstance(z, dict) and z.get("zone_id")]
        return []

    def _extract_device_ids(self) -> list[str]:
        layout = (self.policy or {}).get("zone_layout") or {}
        placement = layout.get("device_placement") or []
        if isinstance(placement, list):
            return [str(p.get("device_id", "")) for p in placement if isinstance(p, dict) and p.get("device_id")]
        return []

    def _extract_device_zone(self) -> dict[str, str]:
        layout = (self.policy or {}).get("zone_layout") or {}
        placement = layout.get("device_placement") or []
        out = {}
        for p in placement if isinstance(placement, list) else []:
            if isinstance(p, dict) and p.get("device_id"):
                out[p["device_id"]] = p.get("zone_id", "")
        return out

    def _extract_adjacency(self) -> set[tuple[str, str]]:
        from labtrust_gym.engine.zones import build_adjacency_set

        layout = (self.policy or {}).get("zone_layout") or {}
        edges = layout.get("graph_edges") or []
        return build_adjacency_set(edges)

    @property
    def state_hash(self) -> str:
        """Stable hash of obs (and t) for tracing."""
        if not self._state_hash:
            canonical = {"t": self.t, "agents": self.agent_ids}
            for aid in self.agent_ids:
                o = self.obs.get(aid) or {}
                canonical[aid] = {
                    k: o[k]
                    for k in sorted(o.keys())
                    if k in ("zone_id", "my_zone_idx", "queue_has_head", "queue_by_device")
                }
            self._state_hash = _stable_hash(canonical)
        return self._state_hash


@runtime_checkable
class Allocator(Protocol):
    """Chooses which agent(s) own which work items (specimens/runs/transports)."""

    def allocate(self, context: KernelContext) -> AllocationDecision:
        """Produce allocation from context. Must be deterministic given context.rng."""
        ...


@runtime_checkable
class Scheduler(Protocol):
    """Sequences owned work items per agent/device with deadlines and priorities."""

    def schedule(
        self,
        context: KernelContext,
        allocation: AllocationDecision,
    ) -> ScheduleDecision:
        """Produce per-agent schedule from allocation. Deterministic given context.rng."""
        ...


@runtime_checkable
class Router(Protocol):
    """Produces safe movement/zone transitions (or reservations) to execute scheduled steps."""

    def route(
        self,
        context: KernelContext,
        allocation: AllocationDecision,
        schedule: ScheduleDecision,
    ) -> RouteDecision:
        """Produce per-agent route (next action). Deterministic given context.rng."""
        ...
