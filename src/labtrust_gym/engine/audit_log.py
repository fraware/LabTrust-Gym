"""
Append-only audit log implemented as a hash chain.

Events are serialized in a canonical way (sorted keys, stable encoding), then
chained with SHA-256: each event's hash depends on the previous hash and the
event bytes. This supports integrity checks and forensic freeze: if the chain
is broken, the system sets log_frozen=True and uses reason code AUDIT_CHAIN_BROKEN.

Fault injection for tests: when initial_state includes break_hash_prev_on_event_id,
the chain is deliberately broken at that event so that freeze behavior can be verified.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_serialize(event: dict[str, Any]) -> bytes:
    """
    Deterministic serialization of an event dict: sorted keys, stable encoding.
    Used for hash chain computation.
    """
    return json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def hash_event(prev_hash: str, event_bytes: bytes) -> str:
    """SHA-256 of prev_hash || event_bytes. prev_hash and result are hex strings."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(event_bytes)
    return h.hexdigest()


class AuditLog:
    """
    Append-only hash chain. Supports fault injection for testing forensic freeze.
    """

    def __init__(self, fault_injection: dict[str, Any] | None = None) -> None:
        self._fault_injection = fault_injection or {}
        self._break_hash_prev_on_event_id: str | None = self._fault_injection.get("break_hash_prev_on_event_id")
        self._head_hash: str = ""
        self._last_event_hash: str = ""
        self._length: int = 0
        self._event_hashes: list[str] = []

    @property
    def head_hash(self) -> str:
        return self._head_hash

    @property
    def last_event_hash(self) -> str:
        return self._last_event_hash

    @property
    def length(self) -> int:
        return self._length

    def append(self, event: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """
        Append an event to the chain. Returns (hashchain_dict, chain_broken).

        hashchain_dict has head_hash, length, last_event_hash.
        chain_broken is True when fault injection was used for this event_id
        (wrong prev_hash used), so the chain is invalid and caller should set
        log_frozen and emit FORENSIC_FREEZE_LOG.
        """
        event_bytes = canonical_serialize(event)
        prev = self._last_event_hash
        event_id = event.get("event_id")
        break_on = self._break_hash_prev_on_event_id
        if break_on and event_id == break_on:
            prev = "broken"
        event_hash = hash_event(prev, event_bytes)

        self._event_hashes.append(event_hash)
        self._length += 1
        if self._length == 1:
            self._head_hash = event_hash
        self._last_event_hash = event_hash

        chain_broken = break_on is not None and event_id == break_on
        out = {
            "head_hash": self._head_hash,
            "length": self._length,
            "last_event_hash": self._last_event_hash,
        }
        return out, chain_broken

    def hashchain_snapshot(self) -> dict[str, Any]:
        """Current hashchain state for step() return."""
        return {
            "head_hash": self._head_hash,
            "length": self._length,
            "last_event_hash": self._last_event_hash,
        }
