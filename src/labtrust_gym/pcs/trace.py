"""PCS workflow trace model with hash-chained events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from labtrust_gym.pcs.hash import GENESIS_EVENT_HASH, canonical_json, pcs_digest, sha256_hex

REQUIRED_ACTIONS = (
    "accession_sample",
    "perform_qc",
    "record_analysis",
    "release_sample",
)

TRACE_EVENT_FIELDS = (
    "event_id",
    "run_id",
    "sample_id",
    "timestamp",
    "actor_id",
    "actor_role",
    "action",
    "pre_state",
    "post_state",
    "policy_decision",
    "reason_code",
    "event_hash",
    "previous_event_hash",
)


@dataclass
class TraceBuilder:
    run_id: str
    sample_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def append_event(
        self,
        *,
        event_id: str,
        timestamp: str,
        actor_id: str,
        actor_role: str,
        action: str,
        pre_state: dict[str, Any],
        post_state: dict[str, Any],
        policy_decision: str,
        reason_code: str,
    ) -> dict[str, Any]:
        previous = self.events[-1]["event_hash"] if self.events else GENESIS_EVENT_HASH
        body = {
            "event_id": event_id,
            "run_id": self.run_id,
            "sample_id": self.sample_id,
            "timestamp": timestamp,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "action": action,
            "pre_state": pre_state,
            "post_state": post_state,
            "policy_decision": policy_decision,
            "reason_code": reason_code,
            "previous_event_hash": previous,
        }
        event_hash = sha256_hex(canonical_json(body))
        event = {**body, "event_hash": event_hash}
        self.events.append(event)
        return event

    def to_trace_document(self) -> dict[str, Any]:
        return {
            "version": "0",
            "artifact_kind": "Trace",
            "run_id": self.run_id,
            "sample_id": self.sample_id,
            "events": list(self.events),
            "trace_hash": compute_trace_hash(
                self.events, run_id=self.run_id, sample_id=self.sample_id
            ),
        }


def compute_trace_hash(
    events: list[dict[str, Any]],
    *,
    run_id: str,
    sample_id: str,
) -> str:
    body = {
        "version": "0",
        "run_id": run_id,
        "sample_id": sample_id,
        "event_hashes": [e["event_hash"] for e in events],
    }
    return pcs_digest(body)


def verify_event_hash_chain(events: list[dict[str, Any]]) -> list[str]:
    """Return validation errors for the hash chain (empty if valid)."""
    errors: list[str] = []
    prev = GENESIS_EVENT_HASH
    for i, event in enumerate(events):
        for key in TRACE_EVENT_FIELDS:
            if key not in event:
                errors.append(f"event[{i}]: missing field {key}")
        if event.get("previous_event_hash") != prev:
            errors.append(f"event[{i}]: previous_event_hash mismatch")
        body = {k: event[k] for k in event if k != "event_hash"}
        expected = sha256_hex(canonical_json(body))
        if event.get("event_hash") != expected:
            errors.append(f"event[{i}]: event_hash mismatch")
        prev = event.get("event_hash", "")
    return errors
