"""
Per-agent view replicas: lag behind global blackboard; snapshot yields minimal state for policies.

ViewReplica.apply(event) updates local state from a delivered event.
ViewReplica.snapshot() returns minimal state: queue heads, zone occupancy, device status, specimen statuses.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from labtrust_gym.coordination.blackboard import BlackboardEvent

# Event types we interpret for view state
TYPE_QUEUE_HEAD = "QUEUE_HEAD"
TYPE_ZONE_OCCUPANCY = "ZONE_OCCUPANCY"
TYPE_DEVICE_STATUS = "DEVICE_STATUS"
TYPE_SPECIMEN_STATUS = "SPECIMEN_STATUS"
TYPE_AGENT_ZONE = "AGENT_ZONE"


class ViewReplica:
    """
    Local view for one agent. Apply events in order; snapshot() returns
    minimal state used by policies (queue heads, zone occupancy, device status, specimen statuses).
    """

    __slots__ = (
        "_agent_id",
        "_last_event_id",
        "_last_processing_step",
        "_last_event_t_event",
        "_queue_heads",
        "_zone_occupancy",
        "_device_status",
        "_specimen_statuses",
        "_agent_zones",
    )

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._last_event_id = -1
        self._last_processing_step: int | None = None
        self._last_event_t_event: int | None = None
        self._queue_heads: dict[str, str | None] = {}
        self._zone_occupancy: dict[str, list[str]] = defaultdict(list)
        self._device_status: dict[str, str] = {}
        self._specimen_statuses: dict[str, dict[str, Any]] = {}
        self._agent_zones: dict[str, str] = {}

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def apply(self, event: BlackboardEvent, processing_step: int | None = None) -> None:
        """
        Apply one event to this replica. Updates internal state from payload_small.
        processing_step: decision_time step when this event was delivered (for staleness).
        """
        if event.id <= self._last_event_id:
            return
        self._last_event_id = event.id
        if processing_step is not None:
            self._last_processing_step = processing_step
        self._last_event_t_event = event.t_event
        p = event.payload_small or {}
        if event.type == TYPE_QUEUE_HEAD:
            dev = p.get("device_id")
            work_id = p.get("queue_head_work_id")
            if dev is not None:
                self._queue_heads[str(dev)] = work_id
        elif event.type == TYPE_ZONE_OCCUPANCY:
            zone_id = p.get("zone_id")
            agents = p.get("agent_ids")
            if zone_id and isinstance(agents, list):
                self._zone_occupancy[str(zone_id)] = [str(a) for a in agents]
        elif event.type == TYPE_DEVICE_STATUS:
            dev = p.get("device_id")
            status = p.get("status")
            if dev is not None and status is not None:
                self._device_status[str(dev)] = str(status)
        elif event.type == TYPE_SPECIMEN_STATUS:
            spec_id = p.get("specimen_id")
            if spec_id is not None:
                self._specimen_statuses[str(spec_id)] = dict(p)
        elif event.type == TYPE_AGENT_ZONE:
            aid = p.get("agent_id")
            zone_id = p.get("zone_id")
            if aid is not None and zone_id is not None:
                self._agent_zones[str(aid)] = str(zone_id)

    def apply_batch(
        self,
        events: list[BlackboardEvent],
        processing_step: int | None = None,
    ) -> None:
        """Apply events in order (e.g. after delivery from CommsModel)."""
        for ev in sorted(events, key=lambda e: e.id):
            self.apply(ev, processing_step=processing_step)

    def snapshot(self) -> dict[str, Any]:
        """
        Minimal state used by policies: queue heads, zone occupancy, device status, specimen statuses.
        Includes last_processing_step and last_event_t_event for timing/staleness.
        """
        return {
            "queue_heads": dict(self._queue_heads),
            "zone_occupancy": {k: list(v) for k, v in self._zone_occupancy.items()},
            "device_status": dict(self._device_status),
            "specimen_statuses": dict(self._specimen_statuses),
            "agent_zones": dict(self._agent_zones),
            "last_event_id": self._last_event_id,
            "last_processing_step": self._last_processing_step,
            "last_event_t_event": self._last_event_t_event,
        }

    @property
    def last_event_id(self) -> int:
        """Last applied event id (for comms delivery tracking)."""
        return self._last_event_id
