"""
Event-sourced blackboard: append-only log of facts with deterministic ordering and replay.

BlackboardEvent: id, t_event, t_emit, type, payload_hash, payload_small.
BlackboardLog: append, head_hash, replay.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Max bytes for payload_small (keep events compact for audit)
PAYLOAD_SMALL_MAX_BYTES = 512


def _stable_hash(obj: Any) -> str:
    """Deterministic SHA-256 hash of JSON-serializable obj (first 16 hex chars)."""
    try:
        payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        payload = repr(obj)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class BlackboardEvent:
    """
    Single immutable fact in the blackboard log.
    id: unique event index (monotonic seq, order in log).
    t_event: event_time = logical step when the fact occurred (engine step).
    t_emit: logical step when the fact was emitted to the log.
    type: event type (e.g. QUEUE_HEAD, ZONE_OCCUPANCY, DEVICE_STATUS, SPECIMEN_STATUS).
    payload_hash: deterministic hash of full payload for integrity.
    payload_small: compact summary for audit (truncated if needed).
    """

    id: int
    t_event: int
    t_emit: int
    type: str
    payload_hash: str
    payload_small: Dict[str, Any]

    @property
    def seq(self) -> int:
        """Monotonic sequence number (same as id)."""
        return self.id

    def to_replay_dict(self) -> Dict[str, Any]:
        """Minimal dict for replay (no large blobs)."""
        return {
            "id": self.id,
            "t_event": self.t_event,
            "t_emit": self.t_emit,
            "type": self.type,
            "payload_hash": self.payload_hash,
            "payload_small": self.payload_small,
        }


class BlackboardLog:
    """
    Append-only event log. Deterministic ordering; replay yields same sequence.
    head_hash chains events for integrity.
    """

    __slots__ = ("_events", "_head_hash", "_next_id")

    def __init__(self) -> None:
        self._events: List[BlackboardEvent] = []
        self._head_hash = ""
        self._next_id = 0

    def append(
        self,
        t_event: int,
        t_emit: int,
        event_type: str,
        payload: Dict[str, Any],
    ) -> BlackboardEvent:
        """
        Append one event. payload_small is payload truncated to PAYLOAD_SMALL_MAX_BYTES.
        Returns the appended event.
        """
        payload_hash = _stable_hash(payload)
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if len(raw.encode("utf-8")) <= PAYLOAD_SMALL_MAX_BYTES:
            try:
                payload_small = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                payload_small = {"_raw": raw[:200]}
        else:
            payload_small = {"_h": payload_hash, "_len": len(raw)}
        ev = BlackboardEvent(
            id=self._next_id,
            t_event=t_event,
            t_emit=t_emit,
            type=event_type,
            payload_hash=payload_hash,
            payload_small=payload_small,
        )
        self._next_id += 1
        self._events.append(ev)
        chain = f"{self._head_hash}|{ev.id}:{ev.payload_hash}"
        self._head_hash = hashlib.sha256(chain.encode("utf-8")).hexdigest()[:24]
        return ev

    @property
    def head_hash(self) -> str:
        """Current chain hash (empty if no events)."""
        return self._head_hash

    @property
    def events(self) -> List[BlackboardEvent]:
        """Read-only list of all events in order."""
        return list(self._events)

    def events_since(self, after_id: int) -> List[BlackboardEvent]:
        """Events with id > after_id, in order."""
        return [e for e in self._events if e.id > after_id]

    def replay(self) -> List[Dict[str, Any]]:
        """Replay all events as list of dicts (deterministic)."""
        return [e.to_replay_dict() for e in self._events]

    def __len__(self) -> int:
        return len(self._events)
