"""
Coordination telemetry: canonical serialization and schema validation for the
coord method output contract (one timestep). Used by the runner to build and
validate coord_decisions.jsonl.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _canonical_json(obj: Any) -> str:
    """Canonical JSON (sort_keys, no extra whitespace) for deterministic hashes."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def build_contract_record(
    method_id: str,
    t_step: int,
    actions_dict: dict[str, dict[str, Any]],
    view_age_ms: float | None = None,
    view_age_ms_per_agent: dict[str, float] | None = None,
    plan_time_ms: float | None = None,
    invariants_considered: list[str] | None = None,
    safety_shield_applied: bool = False,
    safety_shield_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build one timestep record conforming to coord_method_output_contract.v0.1.
    actions_dict: agent_id -> {action_index, action_type?, args?}.
    """
    actions: list[dict[str, Any]] = []
    for agent_id in sorted(actions_dict.keys()):
        ad = actions_dict[agent_id] or {}
        entry: dict[str, Any] = {"agent_id": agent_id}
        if "action_index" in ad:
            entry["action_index"] = int(ad["action_index"])
        if ad.get("action_type") is not None:
            entry["action_type"] = str(ad["action_type"])
        if ad.get("args") is not None and isinstance(ad["args"], dict):
            entry["args"] = dict(ad["args"])
        actions.append(entry)

    record: dict[str, Any] = {
        "method_id": method_id,
        "t_step": t_step,
        "actions": actions,
    }
    if view_age_ms is not None:
        record["view_age_ms"] = round(view_age_ms, 2)
    if view_age_ms_per_agent:
        record["view_age_ms_per_agent"] = {k: round(v, 2) for k, v in view_age_ms_per_agent.items()}
    if plan_time_ms is not None:
        record["plan_time_ms"] = round(plan_time_ms, 2)
    if invariants_considered is not None:
        record["invariants_considered"] = list(invariants_considered)
    record["safety_shield_applied"] = safety_shield_applied
    if safety_shield_details is not None:
        record["safety_shield_details"] = safety_shield_details
    return record


def validate_contract_record(
    record: dict[str, Any],
    schema_path: Path | None = None,
) -> list[str]:
    """
    Validate record against coord_method_output_contract.v0.1 schema.
    Returns list of error messages; empty if valid.
    """
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema required for contract validation"]
    if schema_path is None:
        try:
            from labtrust_gym.config import get_repo_root

            root = get_repo_root()
            schema_path = root / "policy" / "schemas"
            schema_path = schema_path / "coord_method_output_contract.v0.1.schema.json"
        except Exception:
            return ["Could not resolve schema path"]
    if not schema_path.is_file():
        return [f"Schema not found: {schema_path}"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=record, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [str(e)]


def serialize_contract_record(record: dict[str, Any]) -> str:
    """One-line canonical JSON for coord_decisions.jsonl."""
    return _canonical_json(record) + "\n"
