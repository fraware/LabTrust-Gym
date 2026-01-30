"""
Per-device work queues with deterministic STAT/URGENT/ROUTINE ordering.

- DeviceQueueItem: work_id, priority_class, enqueued_ts_s, requested_by_agent, reason_code.
- Ordering: priority_rank (STAT=0, URGENT=1, ROUTINE=2), then enqueued_ts_s, then tie_break.
- QueueStore: enqueue, queue_head(device_id), consume_head(device_id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

PriorityClass = Literal["STAT", "URGENT", "ROUTINE"]

PRIORITY_RANK: Dict[str, int] = {
    "STAT": 0,
    "URGENT": 1,
    "ROUTINE": 2,
}


@dataclass
class DeviceQueueItem:
    """Single item in a device queue."""

    work_id: str
    priority_class: PriorityClass
    enqueued_ts_s: int
    requested_by_agent: str
    reason_code: Optional[str] = None
    tie_break: int = 0

    def __lt__(self, other: DeviceQueueItem) -> bool:
        """Stable ordering: priority_rank, then enqueued_ts_s, then tie_break."""
        r1 = PRIORITY_RANK.get(self.priority_class, 99)
        r2 = PRIORITY_RANK.get(other.priority_class, 99)
        if r1 != r2:
            return r1 < r2
        if self.enqueued_ts_s != other.enqueued_ts_s:
            return self.enqueued_ts_s < other.enqueued_ts_s
        return self.tie_break < other.tie_break


@dataclass
class DeviceQueue:
    """Queue for one device; items kept sorted by ordering rule."""

    device_id: str
    items: List[DeviceQueueItem] = field(default_factory=list)
    _next_tie_break: int = 0

    def enqueue(
        self,
        work_id: str,
        priority_class: PriorityClass,
        enqueued_ts_s: int,
        requested_by_agent: str,
        reason_code: Optional[str] = None,
        *,
        allow_duplicate_work_id: bool = True,
    ) -> bool:
        """Append item and re-sort. Returns False if duplicate work_id and duplicates disallowed."""
        if not allow_duplicate_work_id and any(
            it.work_id == work_id for it in self.items
        ):
            return False
        item = DeviceQueueItem(
            work_id=work_id,
            priority_class=priority_class,
            enqueued_ts_s=enqueued_ts_s,
            requested_by_agent=requested_by_agent,
            reason_code=reason_code,
            tie_break=self._next_tie_break,
        )
        self._next_tie_break += 1
        self.items.append(item)
        self.items.sort()
        return True

    def head_work_id(self) -> Optional[str]:
        """Return work_id at front, or None if empty."""
        if not self.items:
            return None
        return self.items[0].work_id

    def consume_head(self) -> Optional[str]:
        """Remove and return work_id at front; None if empty."""
        if not self.items:
            return None
        work_id = self.items.pop(0).work_id
        return work_id


class QueueStore:
    """
    Per-device queues. Devices are not auto-created; enqueue only for known devices.
    """

    def __init__(self) -> None:
        self._queues: Dict[str, DeviceQueue] = {}
        self._known_device_ids: Optional[Dict[str, Any]] = None

    def set_known_devices(self, device_ids: List[str]) -> None:
        """Set the set of valid device ids (e.g. from zone device_placement)."""
        self._known_device_ids = {d: True for d in device_ids}

    def is_known_device(self, device_id: str) -> bool:
        if self._known_device_ids is None:
            return True
        return device_id in self._known_device_ids

    def _queue(self, device_id: str) -> DeviceQueue:
        if device_id not in self._queues:
            self._queues[device_id] = DeviceQueue(device_id=device_id)
        return self._queues[device_id]

    def enqueue(
        self,
        device_id: str,
        work_id: str,
        priority_class: PriorityClass,
        enqueued_ts_s: int,
        requested_by_agent: str,
        reason_code: Optional[str] = None,
        *,
        allow_duplicate_work_id: bool = True,
    ) -> bool:
        """Enqueue one item. Returns False if device unknown or duplicate work_id disallowed."""
        if not self.is_known_device(device_id):
            return False
        return self._queue(device_id).enqueue(
            work_id,
            priority_class,
            enqueued_ts_s,
            requested_by_agent,
            reason_code,
            allow_duplicate_work_id=allow_duplicate_work_id,
        )

    def queue_head(self, device_id: str) -> Optional[str]:
        """Return work_id at front of device queue, or None if empty/unknown."""
        if device_id not in self._queues:
            return None
        return self._queues[device_id].head_work_id()

    def queue_length(self, device_id: str) -> int:
        """Return number of items in device queue; 0 if unknown or empty."""
        if device_id not in self._queues:
            return 0
        return len(self._queues[device_id].items)

    def consume_head(self, device_id: str) -> Optional[str]:
        """Remove and return work_id at front; None if empty/unknown."""
        if device_id not in self._queues:
            return None
        return self._queues[device_id].consume_head()
