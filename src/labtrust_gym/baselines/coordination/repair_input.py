"""
Deterministic repair input for llm_repair_over_kernel_whca.

Stable ordering, no timestamps: same logical input produces same JSON and hash.
Used for LLM repair backend input and for determinism (llm_offline).
"""

from __future__ import annotations

import hashlib
from typing import Any

from labtrust_gym.baselines.coordination.llm_contract import canonical_json


def build_repair_input(
    scale_config_snapshot: dict[str, Any],
    last_accepted_plan_summary: dict[str, Any],
    blocked_actions: list[dict[str, Any]],
    constraint_summary: dict[str, Any],
    red_team_flags: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build a deterministic repair input dict (stable key order, no timestamps).

    - scale_config_snapshot: sanitized scale config (sorted keys when serialized).
    - last_accepted_plan_summary: e.g. {"route_hash": "...", "step_idx": N} (no wall-clock).
    - blocked_actions: list of {"agent_id", "action_type", "reason_code"} in stable order.
    - constraint_summary: allowed_actions and invariants (INV-ROUTE-001, INV-ROUTE-002).
    - red_team_flags: optional list e.g. ["comms_poison"]; sorted for stability.
    """
    # Snapshot with sorted keys for determinism
    scale_sorted = dict(sorted((k, v) for k, v in (scale_config_snapshot or {}).items()))
    plan_sorted = dict(sorted((k, v) for k, v in (last_accepted_plan_summary or {}).items()))
    constraint_sorted = dict(sorted((k, v) for k, v in (constraint_summary or {}).items()))

    # Blocked actions: sort by (agent_id, action_type, reason_code) for stable order
    blocked = list(blocked_actions or [])
    blocked_normalized = []
    for b in blocked:
        item = {
            "agent_id": str(b.get("agent_id", "")),
            "action_type": str(b.get("action_type", "NOOP")),
            "reason_code": str(b.get("reason_code", "")),
        }
        blocked_normalized.append(item)
    blocked_normalized.sort(key=lambda x: (x["agent_id"], x["action_type"], x["reason_code"]))

    flags = sorted(red_team_flags or [])

    return {
        "scale_config_snapshot": scale_sorted,
        "last_accepted_plan_summary": plan_sorted,
        "blocked_actions": blocked_normalized,
        "constraint_summary": constraint_sorted,
        "red_team_flags": flags,
    }


def repair_input_hash(repair_input: dict[str, Any]) -> str:
    """Stable hash of repair input (same input -> same JSON -> same hash)."""
    canonical = canonical_json(repair_input)
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return h[:32]
