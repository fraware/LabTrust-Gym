"""
Data models for coordination kernel decisions: allocation, schedule, route.

Used for composable methods and COORD_DECISION audit emit. All fields
support deterministic hashing for tracing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AllocationDecision:
    """
    Which agent(s) own which work items.
    assignments: list of (agent_id, work_id, device_id, priority) or equivalent.
    explain: short summary for audit (no large blobs).
    """

    assignments: tuple[tuple[str, str, str, int], ...] = ()
    explain: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.assignments, tuple):
            object.__setattr__(self, "assignments", tuple(self.assignments))


@dataclass(frozen=True)
class ScheduleDecision:
    """
    Per-agent sequence of work with deadlines/priorities.
    per_agent: agent_id -> list of (work_id, deadline_step, priority).
    explain: short summary for audit.
    """

    per_agent: tuple[tuple[str, tuple[tuple[str, int, int], ...]], ...] = ()
    explain: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.per_agent, tuple):
            object.__setattr__(self, "per_agent", tuple(self.per_agent))


@dataclass(frozen=True)
class RouteDecision:
    """
    Safe movement/zone transitions or reservations per agent.
    per_agent: tuple of (agent_id, action_type, args_tuple) with args_tuple
    as tuple of (key, value) for hashability (e.g. ("to_zone", "Z_A"), ("device_id", "DEV_1")).
    explain: short summary for audit.
    """

    per_agent: tuple[tuple[str, str, tuple[tuple[str, Any], ...]], ...] = ()
    explain: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.per_agent, tuple):
            object.__setattr__(self, "per_agent", tuple(self.per_agent))


@dataclass
class CoordinationDecision:
    """
    Full kernel decision for one step: allocation + schedule + route,
    with hashes and compact explain for COORD_DECISION emit.
    """

    method_id: str
    step_idx: int
    seed: int
    state_hash: str
    allocation_hash: str
    schedule_hash: str
    route_hash: str
    allocation: AllocationDecision
    schedule: ScheduleDecision
    route: RouteDecision
    explain_allocation: str = ""
    explain_schedule: str = ""
    explain_route: str = ""

    def to_emit_payload(self) -> Dict[str, Any]:
        """Compact payload for COORD_DECISION emit (no large blobs)."""
        return {
            "method_id": self.method_id,
            "step_idx": self.step_idx,
            "seed": self.seed,
            "state_hash": self.state_hash,
            "allocation_hash": self.allocation_hash,
            "schedule_hash": self.schedule_hash,
            "route_hash": self.route_hash,
            "explain_allocation": (self.explain_allocation or self.allocation.explain)[
                :200
            ],
            "explain_schedule": (self.explain_schedule or self.schedule.explain)[:200],
            "explain_route": (self.explain_route or self.route.explain)[:200],
        }
