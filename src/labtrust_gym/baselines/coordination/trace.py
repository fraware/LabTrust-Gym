"""
METHOD_TRACE.jsonl: one JSON object per decision stage for conformance evidence contract.
Stable enough to diff in CI (same seed -> same trace content).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.util.json_utils import canonical_json


def build_method_trace_event(
    method_id: str,
    t_step: int,
    stage: str,
    duration_ms: float | None = None,
    outcome: str | None = None,
    hash_or_summary: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build one trace event (conforms to method_trace_event.v0.1)."""
    event: dict[str, Any] = {
        "method_id": method_id,
        "t_step": t_step,
        "stage": stage,
    }
    if duration_ms is not None:
        event["duration_ms"] = round(duration_ms, 2)
    if outcome is not None:
        event["outcome"] = outcome
    if hash_or_summary is not None:
        event["hash_or_summary"] = hash_or_summary
    for k, v in extra.items():
        if v is not None and k not in event:
            event[k] = v
    return event


def trace_event_hash(event: dict[str, Any]) -> str:
    """Stable hash for one trace event (for stability assertion)."""
    return hashlib.sha256(canonical_json(event).encode("utf-8")).hexdigest()[:16]


def append_trace_event(trace_path: Path, event: dict[str, Any]) -> None:
    """Append one JSON line to METHOD_TRACE.jsonl."""
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as f:
        f.write(canonical_json(event) + "\n")


def trace_from_contract_record(
    method_id: str,
    t_step: int,
    actions_dict: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Minimal trace event from a step (for runners that do not emit stage-level trace)."""
    h = hashlib.sha256(
        canonical_json({"method_id": method_id, "t_step": t_step, "actions": actions_dict}).encode("utf-8")
    ).hexdigest()[:16]
    return build_method_trace_event(
        method_id=method_id,
        t_step=t_step,
        stage="propose",
        hash_or_summary=h,
    )
