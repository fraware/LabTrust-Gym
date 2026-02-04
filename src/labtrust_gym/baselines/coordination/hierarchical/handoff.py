"""
Handoff protocol: cross-region work transfer with acceptance/ACK and escalation.
HandoffEvent: work_id, from_region, to_region, created_t, ack_by_t.
Missing ACK within T steps triggers escalation (fallback to hub reroute).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_ACK_DEADLINE_STEPS = 10


@dataclass
class HandoffEvent:
    work_id: str
    device_id: str
    from_region: str
    to_region: str
    zone_id: str
    created_t: int
    ack_by_t: int
    priority: int = 0
    acked: bool = False
    ack_t: Optional[int] = None

    def is_expired(self, t: int) -> bool:
        return not self.acked and t > self.ack_by_t

    def to_tuple(self) -> Tuple[str, str, str, str, str, int, int, int]:
        return (
            self.work_id,
            self.device_id,
            self.from_region,
            self.to_region,
            self.zone_id,
            self.created_t,
            self.ack_by_t,
            self.priority,
        )


HUB_REGION_ID = "HUB"


class HandoffProtocol:
    """
    Tracks pending handoffs (hub->region assignments); records ACKs when local agent
    executes START_RUN; detects timeouts and produces escalation list. Deterministic.
    """

    def __init__(self, ack_deadline_steps: int = DEFAULT_ACK_DEADLINE_STEPS) -> None:
        self._ack_deadline_steps = ack_deadline_steps
        self._pending: List[HandoffEvent] = []
        self._cross_region_count = 0
        self._escalation_count = 0
        self._ack_count = 0

    def create_handoff(
        self,
        work_id: str,
        device_id: str,
        from_region: str,
        to_region: str,
        zone_id: str,
        t: int,
        priority: int = 0,
    ) -> HandoffEvent:
        ev = HandoffEvent(
            work_id=work_id,
            device_id=device_id,
            from_region=from_region,
            to_region=to_region,
            zone_id=zone_id,
            created_t=t,
            ack_by_t=t + self._ack_deadline_steps,
            priority=priority,
        )
        self._pending.append(ev)
        self._cross_region_count += 1
        return ev

    def ack(self, work_id: str, device_id: str, t: int) -> bool:
        for ev in self._pending:
            if not ev.acked and ev.work_id == work_id and ev.device_id == device_id:
                ev.acked = True
                ev.ack_t = t
                self._ack_count += 1
                return True
        return False

    def tick(self, t: int) -> Tuple[List[HandoffEvent], List[HandoffEvent]]:
        """
        Returns (still_pending, escalated).
        Escalated = not acked and t > ack_by_t; removed from pending.
        """
        still_pending: List[HandoffEvent] = []
        escalated: List[HandoffEvent] = []
        for ev in self._pending:
            if ev.acked:
                continue
            if ev.is_expired(t):
                escalated.append(ev)
                self._escalation_count += 1
            else:
                still_pending.append(ev)
        self._pending = still_pending
        return still_pending, escalated

    def pending_for_region(self, region_id: str) -> List[HandoffEvent]:
        return [e for e in self._pending if not e.acked and e.to_region == region_id]

    def has_pending(self, work_id: str, device_id: str, to_region: str) -> bool:
        for e in self._pending:
            if (
                not e.acked
                and e.work_id == work_id
                and e.device_id == device_id
                and e.to_region == to_region
            ):
                return True
        return False

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "cross_region_handoffs": self._cross_region_count,
            "handoff_ack_count": self._ack_count,
            "escalations": self._escalation_count,
            "handoff_fail_rate": (
                self._escalation_count / max(1, self._cross_region_count)
            ),
        }
