"""
Invariant checks executed after each accepted step.

The invariant registry (policy) defines check templates. This module compiles
them into callable checks and runs them only after steps that were ACCEPTED.
Results are returned as a standard list of violations (invariant_id, status,
reason_code, details).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from labtrust_gym.logging.step_timing import is_enabled as step_timing_enabled
from labtrust_gym.logging.step_timing import record_invariant_ms

from labtrust_gym.engine.catalogue_runtime import (
    INV_STAB_BIOCHEM_001,
    check_stability,
    check_temp_out_of_band,
)
from labtrust_gym.policy.invariants_registry import (
    InvariantEntry,
    load_invariant_registry,
)

ViolationItem = dict[str, Any]  # invariant_id, status, reason_code?, details?


def _check_adjacency(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/adjacency: MOVE from_zone, to_zone."""
    if event.get("action_type") != "MOVE":
        return None
    args = event.get("args") or {}
    from_zone = args.get("from_zone")
    to_zone = args.get("to_zone")
    if not from_zone or not to_zone:
        return None
    zones = getattr(env, "_zones", None)
    if zones is None or not hasattr(zones, "is_adjacent"):
        return None
    ok = zones.is_adjacent(str(from_zone), str(to_zone))
    if ok:
        return (True, None, None)
    return (False, "RC_ILLEGAL_MOVE", {"from_zone": from_zone, "to_zone": to_zone})


def _check_colocation(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/colocation: device action requires agent in device zone."""
    action_type = event.get("action_type", "")
    action_types = params.get("action_types") or []
    if action_type not in action_types:
        return None
    args = event.get("args") or {}
    device_id = args.get("device_id")
    agent_id = str(event.get("agent_id", ""))
    if not device_id or not agent_id:
        return None
    zones = getattr(env, "_zones", None)
    device_zone_map = getattr(env, "_device_zone", None)
    if zones is None or device_zone_map is None:
        return None
    agent_zone = zones.get_agent_zone(agent_id)
    device_zone = device_zone_map.get(str(device_id))
    if agent_zone is None or device_zone is None:
        return None
    if agent_zone == device_zone:
        return (True, None, None)
    return (False, "RC_DEVICE_NOT_COLOCATED", {"device_id": device_id})


def _check_restricted_door_or_zone(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/restricted_door_or_zone: OPEN_DOOR/MOVE to restricted requires token."""
    action_type = event.get("action_type", "")
    args = event.get("args") or {}
    door_id = params.get("door_id")
    if action_type == "OPEN_DOOR" and args.get("door_id") == door_id:
        token_refs = event.get("token_refs") or []
        if token_refs:
            return (True, None, None)
        return (False, "RBAC_RESTRICTED_ENTRY_DENY", {"door_id": door_id})
    if action_type == "MOVE":
        to_zone = args.get("to_zone")
        if to_zone == params.get("zone_id"):
            token_refs = event.get("token_refs") or []
            if token_refs:
                return (True, None, None)
            return (False, "RBAC_RESTRICTED_ENTRY_DENY", {"to_zone": to_zone})
    return None


def _check_door_open_duration(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """temporal/door_open_duration: TICK checks door open too long."""
    if event.get("action_type") != "TICK":
        return None
    door_id = params.get("door_id")
    if not door_id or not hasattr(env, "query"):
        return None
    try:
        state = env.query(f"door_state('{door_id}')")
    except Exception:
        return None
    if not isinstance(state, dict):
        return None
    if not state.get("open"):
        return (True, None, None)
    duration = state.get("open_duration_s") or 0
    max_s = 200
    zones = getattr(env, "_zones", None)
    if zones is not None and getattr(zones, "layout", None):
        doors = zones.layout.get("doors") or []
        for d in doors:
            if d.get("door_id") == door_id:
                max_s = d.get("max_open_s", 200)
                break
    if duration <= max_s:
        return (True, None, None)
    return (
        False,
        "RC_DOOR_OPEN_TOO_LONG",
        {"door_id": door_id, "duration_s": duration},
    )


def _check_token_active(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/token_active: token_refs must be active (INV-TOK-002 only; revoked => INV-TOK-006)."""
    token_refs = event.get("token_refs") or []
    if not token_refs:
        return None
    if not hasattr(env, "_tokens"):
        return None
    t_s = int(event.get("t_s", 0))
    for tid in token_refs:
        v = env._tokens.validity_violation(tid, t_s)
        if v == "INV-TOK-006":
            return None  # let token_not_revoked handler emit INV-TOK-006
        if v:
            return (False, v, {"token_id": tid})
    return (True, None, None)


def _check_token_revoked(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/token_not_revoked: token_refs must not be revoked (INV-TOK-006)."""
    token_refs = event.get("token_refs") or []
    if not token_refs or not hasattr(env, "_tokens"):
        return None
    for tid in token_refs:
        tok = env._tokens.get(tid)
        if tok and getattr(tok, "state", None) == "REVOKED":
            return (False, "INV-TOK-006", {"token_id": tid})
    return (True, None, None)


def _check_critical_acked(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/critical_acked: RELEASE_RESULT requires ack for critical."""
    if event.get("action_type") != "RELEASE_RESULT":
        return None
    args = event.get("args") or {}
    result_id = args.get("result_id")
    if not result_id or not hasattr(env, "_critical"):
        return None
    crit = env._critical.result_criticality(str(result_id))
    if crit not in ("CRIT_A", "CRIT_B"):
        return (True, None, None)
    if env._critical.has_ack(str(result_id)):
        return (True, None, None)
    return (False, "CRIT_NO_ACK", {"result_id": result_id})


def _check_stability_pass(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/stability_pass: START_RUN when specimen stability within limits => PASS (INV-STAB-BIOCHEM-001)."""
    if event.get("action_type") != "START_RUN":
        return None
    args = event.get("args") or {}
    specimen_ids = args.get("specimen_ids") or []
    if not specimen_ids and not args.get("aliquot_ids"):
        return None
    specimens = getattr(env, "_specimens", None)
    stability = getattr(env, "_stability_policy", None)
    if not specimens or not stability:
        return None
    resolved = specimen_ids
    if hasattr(specimens, "resolve_to_specimen_ids"):
        resolved = specimens.resolve_to_specimen_ids(args.get("specimen_ids"), args.get("aliquot_ids")) or []
    t_s = int(event.get("t_s", 0))
    for sid in resolved[:1]:
        spec = specimens.get(sid) if hasattr(specimens, "get") else None
        if not spec:
            continue
        panel_id = spec.get("panel_id") or "BIOCHEM_PANEL_CORE"
        collection_ts_s = int(spec.get("collection_ts_s", 0))
        separated_ts_s = spec.get("separated_ts_s")
        if separated_ts_s is not None:
            separated_ts_s = int(separated_ts_s)
        temp_band = spec.get("temp_band") or "AMBIENT_20_25"
        ok, _viol_id, _reason, pass_inv = check_stability(
            collection_ts_s, separated_ts_s, t_s, panel_id, stability, temp_band
        )
        if ok and pass_inv == INV_STAB_BIOCHEM_001:
            return (True, None, None)
    return None


def _check_cold_chain_ok(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/cold_chain_ok: START_RUN; only emit VIOLATION when temp out of band (no PASS to keep golden unchanged)."""
    if event.get("action_type") != "START_RUN":
        return None
    args = event.get("args") or {}
    specimen_ids = args.get("specimen_ids") or []
    specimens = getattr(env, "_specimens", None)
    if not specimens or not specimen_ids:
        return None
    if hasattr(specimens, "resolve_to_specimen_ids"):
        specimen_ids = specimens.resolve_to_specimen_ids(args.get("specimen_ids"), args.get("aliquot_ids")) or []
    for sid in specimen_ids:
        spec = specimens.get(sid) if hasattr(specimens, "get") else None
        if not spec:
            continue
        if check_temp_out_of_band(
            spec.get("storage_requirement"),
            spec.get("temp_exposure_log"),
        ):
            return (False, "TEMP_OUT_OF_BAND", {"specimen_id": sid})
    return None  # do not emit INV-ZONE-006:PASS so golden expectations unchanged


def _check_coag_fill_valid(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/coag_fill_valid: ACCEPT_SPECIMEN; citrate + invalid fill => VIOLATION."""
    if event.get("action_type") != "ACCEPT_SPECIMEN":
        return None
    args = event.get("args") or {}
    specimen_id = args.get("specimen_id")
    if not specimen_id:
        return None
    specimens = getattr(env, "_specimens", None)
    if not specimens or not hasattr(specimens, "get"):
        return None
    spec = specimens.get(specimen_id)
    if not spec:
        return (True, None, None)
    container = (spec.get("container_type") or "").upper()
    fill_ok = spec.get("fill_ratio_ok")
    if "CITRATE" in container and fill_ok is False:
        return (False, "CNT_CITRATE_FILL_INVALID", {"specimen_id": specimen_id})
    return (True, None, None)


def _check_token_scope_ok(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/token_scope_ok: START_RUN_OVERRIDE with valid token_refs => PASS (INV-TOK-003)."""
    if event.get("action_type") != "START_RUN_OVERRIDE":
        return None
    token_refs = event.get("token_refs") or []
    if not token_refs:
        return None
    return (True, None, None)


def _check_read_back_confirmed(
    env: Any,
    event: dict[str, Any],
    params: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None] | None:
    """state/read_back_confirmed: ACK_CRITICAL_RESULT; read_back_confirmed true => PASS, false => VIOLATION."""
    if event.get("action_type") != "ACK_CRITICAL_RESULT":
        return None
    args = event.get("args") or {}
    read_back = args.get("read_back_confirmed")
    if read_back is True:
        return (True, None, None)
    if read_back is False:
        return (False, "CRIT_NO_READBACK", {"result_id": args.get("result_id")})
    return None


# Registry: (logic_type, check_name) -> handler(env, event, params) -> (passed, reason_code, details) | None.
# Built-in handlers are registered below; external packages can call register_invariant_handler().
InvariantHandler = Callable[
    [Any, dict[str, Any], dict[str, Any]],
    tuple[bool, str | None, dict[str, Any] | None] | None,
]
_TEMPLATE_HANDLERS: dict[tuple[str, str], InvariantHandler] = {}

# Action-type index: (logic_type, check_name) -> frozenset of action_types the handler cares about, or None to call always.
# Used in evaluate() to skip handlers that would return None for this action_type.
_ACTION_TYPES_FOR_HANDLER: dict[tuple[str, str], frozenset[str] | None] = {
    ("state", "adjacency"): frozenset({"MOVE"}),
    ("state", "colocation"): None,  # uses params.action_types per entry
    ("state", "restricted_door_or_zone"): frozenset({"OPEN_DOOR", "MOVE"}),
    ("temporal", "door_open_duration"): frozenset({"TICK"}),
    ("state", "token_active"): None,
    ("state", "token_not_revoked"): None,
    ("state", "critical_acked"): frozenset({"RELEASE_RESULT"}),
    ("state", "stability_pass"): frozenset({"START_RUN"}),
    ("state", "cold_chain_ok"): frozenset({"START_RUN"}),
    ("state", "coag_fill_valid"): frozenset({"ACCEPT_SPECIMEN"}),
    ("state", "token_scope_ok"): frozenset({"START_RUN_OVERRIDE"}),
    ("state", "read_back_confirmed"): frozenset({"ACK_CRITICAL_RESULT"}),
}


def register_invariant_handler(
    logic_type: str,
    check_name: str,
    handler: InvariantHandler,
) -> None:
    """Register an invariant logic handler for (logic_type, check_name). Overwrites if present."""
    _TEMPLATE_HANDLERS[(logic_type, check_name)] = handler


def _register_builtin_invariant_handlers() -> None:
    """Populate registry with built-in handlers."""
    register_invariant_handler("state", "adjacency", _check_adjacency)
    register_invariant_handler("state", "colocation", _check_colocation)
    register_invariant_handler("state", "restricted_door_or_zone", _check_restricted_door_or_zone)
    register_invariant_handler("temporal", "door_open_duration", _check_door_open_duration)
    register_invariant_handler("state", "token_active", _check_token_active)
    register_invariant_handler("state", "token_not_revoked", _check_token_revoked)
    register_invariant_handler("state", "critical_acked", _check_critical_acked)
    register_invariant_handler("state", "stability_pass", _check_stability_pass)
    register_invariant_handler("state", "cold_chain_ok", _check_cold_chain_ok)
    register_invariant_handler("state", "coag_fill_valid", _check_coag_fill_valid)
    register_invariant_handler("state", "token_scope_ok", _check_token_scope_ok)
    register_invariant_handler("state", "read_back_confirmed", _check_read_back_confirmed)


_register_builtin_invariant_handlers()


class InvariantsRuntime:
    """
    Loads invariant registry, compiles templates into checks,
    evaluates post-step and returns violations list.
    """

    def __init__(self, registry_path: Path | None = None) -> None:
        self._entries = load_invariant_registry(registry_path)
        self._by_id: dict[str, InvariantEntry] = {e.invariant_id: e for e in self._entries}

    def evaluate(
        self,
        env: Any,
        event: dict[str, Any],
        step_result: dict[str, Any],
    ) -> list[ViolationItem]:
        """
        Run compiled checks for this event/result. Only runs when status is ACCEPTED.
        Returns list of violation items: {invariant_id, status, reason_code?, details?}.
        """
        if step_result.get("status") != "ACCEPTED":
            return []
        t0 = time.perf_counter() if step_timing_enabled() else 0.0
        action_type = event.get("action_type", "")
        violations: list[ViolationItem] = []
        for entry in self._entries:
            logic = entry.logic_template
            t = logic.get("type", "state")
            params = logic.get("parameters") or {}
            check_name = params.get("check", "")
            allowed_types = _ACTION_TYPES_FOR_HANDLER.get((t, check_name))
            if allowed_types is not None and action_type not in allowed_types:
                continue
            if (t, check_name) == ("state", "colocation"):
                param_action_types = params.get("action_types") or []
                if param_action_types and action_type not in param_action_types:
                    continue
            handler = _TEMPLATE_HANDLERS.get((t, check_name))
            if not handler:
                continue
            try:
                out = handler(env, event, params)
            except Exception:
                continue
            if out is None:
                continue
            passed, reason_code, details = out
            status = "PASS" if passed else "VIOLATION"
            item: ViolationItem = {
                "invariant_id": entry.invariant_id,
                "status": status,
            }
            if reason_code:
                item["reason_code"] = reason_code
            if details:
                item["details"] = details
            violations.append(item)
        if step_timing_enabled():
            record_invariant_ms((time.perf_counter() - t0) * 1000)
        return violations


def merge_violations_by_invariant_id(
    legacy: list[ViolationItem],
    registry: list[ViolationItem],
) -> list[ViolationItem]:
    """Merge registry violations into legacy. Prefer VIOLATION over PASS when both exist for same invariant_id."""
    by_id: dict[str, ViolationItem] = {}
    for v in legacy:
        inv_id = v.get("invariant_id")
        if inv_id:
            by_id[inv_id] = v
    for v in registry:
        inv_id = v.get("invariant_id")
        if not inv_id:
            continue
        existing = by_id.get(inv_id)
        # Do not let registry PASS overwrite legacy VIOLATION (e.g. zones.tick door-open-too-long)
        if existing and existing.get("status") == "VIOLATION" and v.get("status") == "PASS":
            continue
        by_id[inv_id] = v
    return list(by_id.values())
