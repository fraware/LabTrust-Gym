"""
Transition-level tests for every CoreEnv action in _STEP_DISPATCH / _STEP_DISPATCH_LATE.

LTG-PR1: each action has a precondition-fail case and a happy path (or documented
illegal edge). Does not re-run the full golden suite.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from labtrust_gym.engine.core_env import (
    _STEP_DISPATCH,
    _STEP_DISPATCH_LATE,
    AUDIT_MISSING_REASON_CODE,
    CoreEnv,
)
from labtrust_gym.engine.rbac import RBAC_ACTION_DENY

DISPATCH_ACTIONS: frozenset[str] = frozenset(_STEP_DISPATCH) | frozenset(_STEP_DISPATCH_LATE)


def _base_initial(
    *,
    specimens: list[dict[str, Any]] | None = None,
    agents: list[dict[str, Any]] | None = None,
    tokens: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": specimens
        if specimens is not None
        else [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": tokens if tokens is not None else [],
    }
    if agents is not None:
        state["agents"] = agents
    if extra:
        state.update(extra)
    return state


def _event(
    action_type: str,
    *,
    agent_id: str,
    args: dict[str, Any] | None = None,
    t_s: int = 100,
    reason_code: str | None = None,
    token_refs: list[str] | None = None,
    event_id: str = "e1",
    rationale: str | None = None,
) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "event_id": event_id,
        "t_s": t_s,
        "agent_id": agent_id,
        "action_type": action_type,
        "args": args or {},
        "reason_code": reason_code,
        "token_refs": token_refs or [],
    }
    if rationale is not None:
        ev["rationale"] = rationale
    return ev


def _reset(env: CoreEnv, initial: dict[str, Any]) -> None:
    env.reset(initial, deterministic=True, rng_seed=12345)


def _snapshot_world(env: CoreEnv) -> dict[str, Any]:
    """Minimal world snapshot for BLOCKED non-mutation asserts."""
    specimens: dict[str, str | None] = {}
    if env._specimens is not None:
        for sid in getattr(env._specimens, "_by_id", {}) or {}:
            specimens[sid] = env._specimens.specimen_status(sid)
    agent_zones: dict[str, str | None] = {}
    if env._zones is not None:
        for aid in ("A_RECEPTION", "A_ANALYTICS", "A_RUNNER", "A_PREAN", "A_SUPERVISOR"):
            agent_zones[aid] = env._zones.get_agent_zone(aid)
    return {
        "log_frozen": bool(env._system_state.get("log_frozen")),
        "specimens": specimens,
        "agent_zones": agent_zones,
        "token_active": list(env._tokens.list_active_ids()),
    }


# ---------------------------------------------------------------------------
# Precondition-fail builders: (env setup fn returning CoreEnv, event) -> None
# Each returns (env, event, expected_blocked_substring_or_None)
# ---------------------------------------------------------------------------

CaseBuilder = Callable[[], tuple[CoreEnv, dict[str, Any], str | None]]


def _fail_rbac(action: str, wrong_agent: str = "A_RECEPTION") -> CaseBuilder:
    def _build() -> tuple[CoreEnv, dict[str, Any], str | None]:
        env = CoreEnv()
        _reset(env, _base_initial())
        return env, _event(action, agent_id=wrong_agent, args={"result_id": "RES_X"}), RBAC_ACTION_DENY

    return _build


def _fail_move_illegal() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "MOVE",
        agent_id="A_RECEPTION",
        args={
            "entity_type": "Agent",
            "entity_id": "A_RECEPTION",
            "from_zone": "Z_SRA_RECEPTION",
            "to_zone": "Z_ANALYZER_HALL_A",
        },
    )
    return env, ev, "RC_ILLEGAL_MOVE"


def _fail_mint_dual_approval() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "MINT_TOKEN",
        agent_id="A_SUPERVISOR",
        args={
            "token_type": "OVERRIDE_RISK_ACCEPTANCE",
            "subject_type": "specimen",
            "subject_id": "S1",
            "reason_code": "TIME_EXPIRED",
            "approvals": ["A_SUPERVISOR"],
        },
        reason_code="TIME_EXPIRED",
    )
    return env, ev, "INV-TOK"


def _fail_open_door_restricted() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "OPEN_DOOR",
        agent_id="A_RUNNER",
        args={"door_id": "D_RESTRICTED_AIRLOCK"},
    )
    return env, ev, "RBAC_RESTRICTED_ENTRY_DENY"


def _fail_centrifuge_not_colocated() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            agents=[{"agent_id": "A_PREAN", "zone_id": "Z_PREANALYTICS"}],
        ),
    )
    ev = _event(
        "CENTRIFUGE_START",
        agent_id="A_PREAN",
        args={"device_id": "DEV_CENTRIFUGE_BANK_01", "specimen_ids": ["S1"]},
    )
    return env, ev, "RC_DEVICE_NOT_COLOCATED"


def _fail_queue_unknown_device() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "QUEUE_RUN",
        agent_id="A_ANALYTICS",
        args={"device_id": "DEV_DOES_NOT_EXIST", "accession_ids": ["S1"]},
    )
    return env, ev, "RC_DEVICE_UNKNOWN"


def _fail_hold_missing_reason() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "HOLD_SPECIMEN",
        agent_id="A_RECEPTION",
        args={"specimen_id": "S1"},
        reason_code=None,
    )
    return env, ev, AUDIT_MISSING_REASON_CODE


def _fail_start_run_not_colocated() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            agents=[{"agent_id": "A_ANALYTICS", "zone_id": "Z_SRA_RECEPTION"}],
            specimens=[{"template_ref": "S_BIOCHEM_OK", "status": "accepted"}],
        ),
    )
    ev = _event(
        "START_RUN",
        agent_id="A_ANALYTICS",
        args={"device_id": "DEV_CHEM_A_01", "run_id": "R1", "specimen_ids": ["S1"]},
    )
    return env, ev, "RC_DEVICE_NOT_COLOCATED"


def _fail_start_run_override_not_colocated() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            agents=[{"agent_id": "A_ANALYTICS", "zone_id": "Z_SRA_RECEPTION"}],
            specimens=[{"template_ref": "S_BIOCHEM_OK", "status": "accepted"}],
        ),
    )
    ev = _event(
        "START_RUN_OVERRIDE",
        agent_id="A_ANALYTICS",
        args={"device_id": "DEV_CHEM_A_01", "run_id": "R1", "specimen_ids": ["S1"]},
        token_refs=["T_MISSING"],
    )
    return env, ev, "RC_DEVICE_NOT_COLOCATED"


def _fail_release_qc_fail() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial(agents=[{"agent_id": "A_ANALYTICS", "zone_id": "Z_ANALYZER_HALL_A"}]))
    assert env._qc is not None
    env._qc.set_device_qc_state("DEV_CHEM_A_01", "fail")
    env._qc.create_result("RES_FAIL", "R_FAIL", device_id="DEV_CHEM_A_01", qc_state="fail")
    ev = _event(
        "RELEASE_RESULT",
        agent_id="A_ANALYTICS",
        args={"result_id": "RES_FAIL"},
    )
    return env, ev, "QC_FAIL_ACTIVE"


def _fail_release_override_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "RELEASE_RESULT_OVERRIDE",
        agent_id="A_RUNNER",
        args={"result_id": "RES1"},
        token_refs=["T_X"],
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_ack_missing_fields() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env._qc is not None and env._critical is not None
    env._qc.create_result("RES_CRIT", "R1", device_id="DEV_CHEM_A_01")
    env._critical.classify_and_set("RES_CRIT", "BIOCHEM_POTASSIUM_K", 7.0, "mmol/L")
    env.step(
        _event(
            "NOTIFY_CRITICAL_RESULT",
            agent_id="A_SUPERVISOR",
            args={
                "result_id": "RES_CRIT",
                "channel": "phone",
                "receiver_role": "primary_contact",
            },
            event_id="e0",
            t_s=90,
        )
    )
    ev = _event(
        "ACK_CRITICAL_RESULT",
        agent_id="A_SUPERVISOR",
        args={
            "result_id": "RES_CRIT",
            "channel": "phone",
            "receiver_role": "primary_contact",
            "receiver_name_or_id": "DR_X",
            "receiver_location_or_org": "WARD_Z",
            "read_back_confirmed": True,
            "outcome": "reached",
        },
        t_s=100,
    )
    return env, ev, "CRIT_ACK_MISSING_FIELDS"


def _fail_escalate_out_of_order() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env._qc is not None and env._critical is not None
    env._qc.create_result("RES_CRIT2", "R1", device_id="DEV_CHEM_A_01")
    env._critical.classify_and_set("RES_CRIT2", "BIOCHEM_POTASSIUM_K", 7.0, "mmol/L")
    env.step(
        _event(
            "NOTIFY_CRITICAL_RESULT",
            agent_id="A_SUPERVISOR",
            args={
                "result_id": "RES_CRIT2",
                "channel": "phone",
                "receiver_role": "primary_contact",
            },
            event_id="e0",
            t_s=90,
        )
    )
    ev = _event(
        "ESCALATE_CRITICAL_RESULT",
        agent_id="A_SUPERVISOR",
        args={"result_id": "RES_CRIT2", "next_role": "duty_manager"},
        t_s=100,
    )
    return env, ev, "CRIT_ESCALATION_OUT_OF_ORDER"


def _fail_dispatch_forbidden() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "DISPATCH_TRANSPORT",
        agent_id="A_ANALYTICS",
        args={
            "specimen_ids": ["S1"],
            "origin_site": "SITE_HUB",
            "dest_site": "SITE_ACUTE",
        },
    )
    return env, ev, "TRANSPORT_ROUTE_FORBIDDEN"


def _fail_receive_unknown() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "RECEIVE_TRANSPORT",
        agent_id="A_ANALYTICS",
        args={"consignment_id": "CONS_DOES_NOT_EXIST"},
    )
    return env, ev, "TRANSPORT"


def _fail_tick_frozen() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    env._system_state["log_frozen"] = True
    ev = _event("TICK", agent_id="A_RECEPTION", args={})
    return env, ev, "AUDIT_CHAIN_BROKEN"


def _fail_revoke_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    return _fail_rbac("REVOKE_TOKEN")()


def _fail_create_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    # A_ANALYTICS cannot CREATE_ACCESSION
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "CREATE_ACCESSION",
        agent_id="A_ANALYTICS",
        args={"specimen_id": "S1"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_check_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "CHECK_ACCEPTANCE_RULES",
        agent_id="A_ANALYTICS",
        args={"specimen_id": "S1"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_accept_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "ACCEPT_SPECIMEN",
        agent_id="A_ANALYTICS",
        args={"specimen_id": "S1"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_reject_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "REJECT_SPECIMEN",
        agent_id="A_ANALYTICS",
        args={"specimen_id": "S1", "reason_code": "ID_MISMATCH"},
        reason_code="ID_MISMATCH",
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_centrifuge_end_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "CENTRIFUGE_END",
        agent_id="A_RECEPTION",
        args={"device_id": "DEV_CENTRIFUGE_BANK_01", "specimen_ids": ["S1"]},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_aliquot_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "ALIQUOT_CREATE",
        agent_id="A_RECEPTION",
        args={"specimen_id": "S1", "aliquot_id": "A1", "device_id": "DEV_ALIQUOTER_01"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_qc_event_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "QC_EVENT",
        agent_id="A_RECEPTION",
        args={"device_id": "DEV_CHEM_A_01", "qc_outcome": "pass"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_generate_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "GENERATE_RESULT",
        agent_id="A_RECEPTION",
        args={"result_id": "RES1", "run_id": "R1"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_hold_result_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "HOLD_RESULT",
        agent_id="A_RECEPTION",
        args={"result_id": "RES1"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_rerun_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "RERUN_REQUEST",
        agent_id="A_RECEPTION",
        args={"result_id": "RES1"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_notify_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "NOTIFY_CRITICAL_RESULT",
        agent_id="A_RECEPTION",
        args={"result_id": "RES1", "channel": "phone", "receiver_role": "clinician"},
    )
    return env, ev, RBAC_ACTION_DENY


def _fail_transport_tick_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event("TRANSPORT_TICK", agent_id="A_RECEPTION", args={})
    return env, ev, RBAC_ACTION_DENY


def _fail_coc_rbac() -> tuple[CoreEnv, dict[str, Any], str | None]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "CHAIN_OF_CUSTODY_SIGN",
        agent_id="A_RECEPTION",
        args={"consignment_id": "C1"},
    )
    return env, ev, RBAC_ACTION_DENY


PRECONDITION_FAIL: dict[str, CaseBuilder] = {
    "TICK": _fail_tick_frozen,
    "MOVE": _fail_move_illegal,
    "MINT_TOKEN": _fail_mint_dual_approval,
    "REVOKE_TOKEN": _fail_revoke_rbac,
    "OPEN_DOOR": _fail_open_door_restricted,
    "CENTRIFUGE_START": _fail_centrifuge_not_colocated,
    "QUEUE_RUN": _fail_queue_unknown_device,
    "CREATE_ACCESSION": _fail_create_rbac,
    "CHECK_ACCEPTANCE_RULES": _fail_check_rbac,
    "ACCEPT_SPECIMEN": _fail_accept_rbac,
    "HOLD_SPECIMEN": _fail_hold_missing_reason,
    "REJECT_SPECIMEN": _fail_reject_rbac,
    "CENTRIFUGE_END": _fail_centrifuge_end_rbac,
    "ALIQUOT_CREATE": _fail_aliquot_rbac,
    "START_RUN": _fail_start_run_not_colocated,
    "START_RUN_OVERRIDE": _fail_start_run_override_not_colocated,
    "QC_EVENT": _fail_qc_event_rbac,
    "GENERATE_RESULT": _fail_generate_rbac,
    "RELEASE_RESULT": _fail_release_qc_fail,
    "HOLD_RESULT": _fail_hold_result_rbac,
    "RERUN_REQUEST": _fail_rerun_rbac,
    "RELEASE_RESULT_OVERRIDE": _fail_release_override_rbac,
    "NOTIFY_CRITICAL_RESULT": _fail_notify_rbac,
    "ACK_CRITICAL_RESULT": _fail_ack_missing_fields,
    "ESCALATE_CRITICAL_RESULT": _fail_escalate_out_of_order,
    "DISPATCH_TRANSPORT": _fail_dispatch_forbidden,
    "TRANSPORT_TICK": _fail_transport_tick_rbac,
    "RECEIVE_TRANSPORT": _fail_receive_unknown,
    "CHAIN_OF_CUSTODY_SIGN": _fail_coc_rbac,
}


# ---------------------------------------------------------------------------
# Happy path / documented illegal-edge builders
# ---------------------------------------------------------------------------

HappyBuilder = Callable[[], tuple[CoreEnv, dict[str, Any], str]]
# Returns (env, event, expected_status) where expected_status is ACCEPTED or BLOCKED


def _happy_tick() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    return env, _event("TICK", agent_id="A_RECEPTION"), "ACCEPTED"


def _happy_move() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "MOVE",
        agent_id="A_RECEPTION",
        args={
            "entity_type": "Agent",
            "entity_id": "A_RECEPTION",
            "from_zone": "Z_SRA_RECEPTION",
            "to_zone": "Z_ACCESSIONING",
        },
    )
    return env, ev, "ACCEPTED"


def _happy_mint() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "MINT_TOKEN",
        agent_id="A_SUPERVISOR",
        args={
            "token_type": "TOKEN_RESTRICTED_ENTRY",
            "subject_type": "door",
            "subject_id": "D_RESTRICTED_AIRLOCK",
            "reason_code": "RESTRICTED_ENTRY",
            "approvals": [
                {
                    "approver_agent_id": "A_SUPERVISOR",
                    "approver_key_id": "ed25519:key_supervisor",
                }
            ],
        },
        reason_code="RESTRICTED_ENTRY",
    )
    return env, ev, "ACCEPTED"


def _happy_revoke() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    mint = _event(
        "MINT_TOKEN",
        agent_id="A_SUPERVISOR",
        args={
            "token_type": "TOKEN_RESTRICTED_ENTRY",
            "subject_type": "door",
            "subject_id": "D_WASTE",
            "reason_code": "RESTRICTED_ENTRY",
            "approvals": [
                {
                    "approver_agent_id": "A_SUPERVISOR",
                    "approver_key_id": "ed25519:key_supervisor",
                }
            ],
        },
        reason_code="RESTRICTED_ENTRY",
        event_id="e0",
    )
    assert env.step(mint)["status"] == "ACCEPTED"
    tid = "T_TOKEN_RESTRICTED_ENTRY_D_WASTE"
    ev = _event("REVOKE_TOKEN", agent_id="A_SUPERVISOR", args={"token_id": tid})
    return env, ev, "ACCEPTED"


def _illegal_open_door_documented() -> tuple[CoreEnv, dict[str, Any], str]:
    """Documented illegal edge (GS-008): restricted door without token -> BLOCKED."""
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "OPEN_DOOR",
        agent_id="A_RUNNER",
        args={"door_id": "D_RESTRICTED_AIRLOCK"},
    )
    return env, ev, "BLOCKED"


def _happy_open_door() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "OPEN_DOOR",
        agent_id="A_RUNNER",
        args={"door_id": "D_MAIN_INNER"},
    )
    return env, ev, "ACCEPTED"


def _happy_centrifuge_start() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            agents=[{"agent_id": "A_PREAN", "zone_id": "Z_CENTRIFUGE_BAY"}],
            specimens=[{"template_ref": "S_BIOCHEM_OK", "status": "accepted"}],
        ),
    )
    ev = _event(
        "CENTRIFUGE_START",
        agent_id="A_PREAN",
        args={"device_id": "DEV_CENTRIFUGE_BANK_01", "specimen_ids": ["S1"]},
    )
    return env, ev, "ACCEPTED"


def _happy_queue_run() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            specimens=[{"template_ref": "S_BIOCHEM_OK", "status": "accepted"}],
        ),
    )
    ev = _event(
        "QUEUE_RUN",
        agent_id="A_ANALYTICS",
        args={"device_id": "DEV_CHEM_A_01", "accession_ids": ["S1"]},
    )
    return env, ev, "ACCEPTED"


def _happy_create() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    return (
        env,
        _event("CREATE_ACCESSION", agent_id="A_RECEPTION", args={"specimen_id": "S1"}),
        "ACCEPTED",
    )


def _happy_check() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    return (
        env,
        _event(
            "CHECK_ACCEPTANCE_RULES",
            agent_id="A_RECEPTION",
            args={"specimen_id": "S1"},
        ),
        "ACCEPTED",
    )


def _happy_accept() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert (
        env.step(
            _event(
                "CREATE_ACCESSION",
                agent_id="A_RECEPTION",
                args={"specimen_id": "S1"},
                event_id="e0",
            )
        )["status"]
        == "ACCEPTED"
    )
    return (
        env,
        _event("ACCEPT_SPECIMEN", agent_id="A_RECEPTION", args={"specimen_id": "S1"}),
        "ACCEPTED",
    )


def _happy_hold() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "HOLD_SPECIMEN",
        agent_id="A_RECEPTION",
        args={"specimen_id": "S1"},
        reason_code="INT_INSUFFICIENT_VOLUME",
    )
    return env, ev, "ACCEPTED"


def _happy_reject() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "REJECT_SPECIMEN",
        agent_id="A_RECEPTION",
        args={"specimen_id": "S1"},
        reason_code="ID_MISMATCH",
    )
    return env, ev, "ACCEPTED"


def _happy_centrifuge_end() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            agents=[{"agent_id": "A_PREAN", "zone_id": "Z_CENTRIFUGE_BAY"}],
            specimens=[{"template_ref": "S_BIOCHEM_OK", "status": "accepted"}],
        ),
    )
    ev = _event(
        "CENTRIFUGE_END",
        agent_id="A_PREAN",
        args={
            "device_id": "DEV_CENTRIFUGE_BANK_01",
            "specimen_ids": ["S1"],
            "separated_ts_s": 200,
        },
        t_s=200,
    )
    return env, ev, "ACCEPTED"


def _happy_aliquot() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            agents=[{"agent_id": "A_PREAN", "zone_id": "Z_ALIQUOT_LABEL"}],
            specimens=[{"template_ref": "S_BIOCHEM_OK", "status": "accepted"}],
        ),
    )
    ev = _event(
        "ALIQUOT_CREATE",
        agent_id="A_PREAN",
        args={
            "device_id": "DEV_ALIQUOTER_01",
            "specimen_id": "S1",
            "aliquot_id": "A1",
        },
    )
    return env, ev, "ACCEPTED"


def _happy_start_run() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            agents=[{"agent_id": "A_ANALYTICS", "zone_id": "Z_ANALYZER_HALL_A"}],
            specimens=[
                {
                    "template_ref": "S_BIOCHEM_OK",
                    "status": "accepted",
                    "separated_ts_s": 50,
                    "collection_ts_s": 0,
                }
            ],
        ),
    )
    assert (
        env.step(
            _event(
                "QUEUE_RUN",
                agent_id="A_ANALYTICS",
                args={"device_id": "DEV_CHEM_A_01", "accession_ids": ["S1"]},
                event_id="e0",
                t_s=60,
            )
        )["status"]
        == "ACCEPTED"
    )
    ev = _event(
        "START_RUN",
        agent_id="A_ANALYTICS",
        args={"device_id": "DEV_CHEM_A_01", "run_id": "R1", "specimen_ids": ["S1"]},
        t_s=70,
    )
    return env, ev, "ACCEPTED"


def _happy_start_run_override() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            agents=[{"agent_id": "A_ANALYTICS", "zone_id": "Z_ANALYZER_HALL_A"}],
            specimens=[{"template_ref": "S_BIOCHEM_OK", "status": "accepted"}],
        ),
    )
    mint = _event(
        "MINT_TOKEN",
        agent_id="A_SUPERVISOR",
        args={
            "token_type": "OVERRIDE_RISK_ACCEPTANCE",
            "subject_type": "specimen",
            "subject_id": "S1",
            "reason_code": "TIME_EXPIRED",
            "approvals": [
                {
                    "approver_agent_id": "A_SUPERVISOR",
                    "approver_key_id": "ed25519:key_supervisor",
                },
                {
                    "approver_agent_id": "A_CLINSCI",
                    "approver_key_id": "ed25519:key_clinsci",
                },
            ],
        },
        reason_code="TIME_EXPIRED",
        event_id="e0",
        t_s=50,
    )
    assert env.step(mint)["status"] == "ACCEPTED"
    ev = _event(
        "START_RUN_OVERRIDE",
        agent_id="A_ANALYTICS",
        args={
            "device_id": "DEV_CHEM_A_01",
            "run_id": "R_OVR",
            "specimen_ids": ["S1"],
            "reason_code": "TIME_EXPIRED",
        },
        reason_code="TIME_EXPIRED",
        rationale="Dual approval override for stability window on S1",
        token_refs=["T_OVR_S1"],
        t_s=60,
    )
    return env, ev, "ACCEPTED"


def _happy_qc_event() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "QC_EVENT",
        agent_id="A_QC",
        args={"device_id": "DEV_CHEM_A_01", "run_id": "R1", "qc_outcome": "pass"},
    )
    return env, ev, "ACCEPTED"


def _happy_generate() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env._qc is not None
    env._qc.register_run("R1", "DEV_CHEM_A_01")
    ev = _event(
        "GENERATE_RESULT",
        agent_id="A_ANALYTICS",
        args={
            "run_id": "R1",
            "result_id": "RES1",
            "analyte_code": "BIOCHEM_CRP",
            "value": 10.0,
            "units": "mg/L",
        },
    )
    return env, ev, "ACCEPTED"


def _happy_release() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env._qc is not None
    env._qc.set_device_qc_state("DEV_CHEM_A_01", "pass")
    env._qc.create_result("RES_OK", "R1", device_id="DEV_CHEM_A_01", qc_state="pass")
    ev = _event(
        "RELEASE_RESULT",
        agent_id="A_ANALYTICS",
        args={"result_id": "RES_OK"},
    )
    return env, ev, "ACCEPTED"


def _happy_hold_result() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env._qc is not None
    env._qc.create_result("RES_H", "R1", device_id="DEV_CHEM_A_01")
    ev = _event(
        "HOLD_RESULT",
        agent_id="A_ANALYTICS",
        args={"result_id": "RES_H"},
    )
    return env, ev, "ACCEPTED"


def _happy_rerun() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    return (
        env,
        _event("RERUN_REQUEST", agent_id="A_ANALYTICS", args={"result_id": "RES1"}),
        "ACCEPTED",
    )


def _happy_release_override() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(
        env,
        _base_initial(
            tokens=[
                {
                    "token_id": "T_QC_DRIFT",
                    "token_type": "TOKEN_QC_DRIFT_OVERRIDE",
                    "state": "ACTIVE",
                    "subject_type": "result",
                    "subject_id": "RES_DRIFT",
                    "issued_at_ts_s": 0,
                    "expires_at_ts_s": 1800,
                    "reason_code": "QC_DRIFT_SUSPECTED",
                }
            ],
        ),
    )
    assert env._qc is not None
    env._qc.create_result("RES_DRIFT", "R1", device_id="DEV_CHEM_A_01", qc_state="drift")
    ev = _event(
        "RELEASE_RESULT_OVERRIDE",
        agent_id="A_ANALYTICS",
        args={"result_id": "RES_DRIFT", "reason_code": "QC_DRIFT_SUSPECTED"},
        reason_code="QC_DRIFT_SUSPECTED",
        rationale="Release with QC drift override token and disclaimer",
        token_refs=["T_QC_DRIFT"],
        t_s=1010,
    )
    return env, ev, "ACCEPTED"


def _happy_notify() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env._qc is not None and env._critical is not None
    env._qc.create_result("RES_N", "R1", device_id="DEV_CHEM_A_01")
    env._critical.classify_and_set("RES_N", "BIOCHEM_CRP", 999.0, "mg/L")
    ev = _event(
        "NOTIFY_CRITICAL_RESULT",
        agent_id="A_SUPERVISOR",
        args={
            "result_id": "RES_N",
            "channel": "phone",
            "receiver_role": "clinician",
        },
    )
    return env, ev, "ACCEPTED"


def _happy_ack() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env._qc is not None and env._critical is not None
    env._qc.create_result("RES_A", "R1", device_id="DEV_CHEM_A_01")
    # Use potassium critical analyte like GS-CRIT-* so ladder/ACK fields apply.
    env._critical.classify_and_set("RES_A", "BIOCHEM_POTASSIUM_K", 7.0, "mmol/L")
    notify_out = env.step(
        _event(
            "NOTIFY_CRITICAL_RESULT",
            agent_id="A_SUPERVISOR",
            args={
                "result_id": "RES_A",
                "channel": "phone",
                "receiver_role": "primary_contact",
            },
            event_id="e0",
            t_s=90,
        )
    )
    assert notify_out["status"] == "ACCEPTED"
    attempt_id = "RES_A_attempt_0"
    ev = _event(
        "ACK_CRITICAL_RESULT",
        agent_id="A_SUPERVISOR",
        args={
            "result_id": "RES_A",
            "attempt_id": attempt_id,
            "channel": "phone",
            "receiver_role": "primary_contact",
            "receiver_name_or_id": "DR_X",
            "receiver_location_or_org": "WARD_Z",
            "read_back_confirmed": True,
            "outcome": "reached",
            "acknowledgment_ts_s": 100,
        },
        t_s=100,
    )
    return env, ev, "ACCEPTED"


def _illegal_escalate_documented() -> tuple[CoreEnv, dict[str, Any], str]:
    """Documented illegal edge (GS-CRIT-024): escalate out of order -> BLOCKED."""
    env, event, _ = _fail_escalate_out_of_order()
    return env, event, "BLOCKED"


def _happy_escalate() -> tuple[CoreEnv, dict[str, Any], str]:
    # Minimal accept path: escalate without forcing out-of-order when next_role empty
    # is too weak; use notify then escalate to first ladder step if possible.
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env._qc is not None and env._critical is not None
    env._qc.create_result("RES_E", "R1", device_id="DEV_CHEM_A_01")
    env._critical.classify_and_set("RES_E", "BIOCHEM_CRP", 999.0, "mg/L")
    # Without next_role, handler accepts (no escalate mutation required)
    ev = _event(
        "ESCALATE_CRITICAL_RESULT",
        agent_id="A_SUPERVISOR",
        args={"result_id": "RES_E"},
    )
    return env, ev, "ACCEPTED"


def _happy_dispatch() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    ev = _event(
        "DISPATCH_TRANSPORT",
        agent_id="A_ANALYTICS",
        args={
            "specimen_ids": ["S1"],
            "origin_site": "SITE_ACUTE",
            "dest_site": "SITE_HUB",
        },
    )
    return env, ev, "ACCEPTED"


def _happy_transport_tick() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    disp = env.step(
        _event(
            "DISPATCH_TRANSPORT",
            agent_id="A_ANALYTICS",
            args={
                "specimen_ids": ["S1"],
                "origin_site": "SITE_ACUTE",
                "dest_site": "SITE_HUB",
            },
            event_id="e0",
            t_s=10,
        )
    )
    assert disp["status"] == "ACCEPTED"
    return env, _event("TRANSPORT_TICK", agent_id="A_ANALYTICS", args={}, t_s=700), "ACCEPTED"


def _happy_receive() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    disp = env.step(
        _event(
            "DISPATCH_TRANSPORT",
            agent_id="A_ANALYTICS",
            args={
                "specimen_ids": ["S1"],
                "origin_site": "SITE_ACUTE",
                "dest_site": "SITE_HUB",
            },
            event_id="e0",
            t_s=10,
        )
    )
    assert disp["status"] == "ACCEPTED"
    cid = disp.get("consignment_id")
    assert cid
    env.step(_event("TRANSPORT_TICK", agent_id="A_ANALYTICS", args={}, event_id="e1", t_s=700))
    # Sign CoC if required before receive
    env.step(
        _event(
            "CHAIN_OF_CUSTODY_SIGN",
            agent_id="A_ANALYTICS",
            args={"consignment_id": cid},
            event_id="e2",
            t_s=710,
        )
    )
    ev = _event(
        "RECEIVE_TRANSPORT",
        agent_id="A_ANALYTICS",
        args={"consignment_id": cid},
        t_s=720,
    )
    return env, ev, "ACCEPTED"


def _happy_coc() -> tuple[CoreEnv, dict[str, Any], str]:
    env = CoreEnv()
    _reset(env, _base_initial())
    disp = env.step(
        _event(
            "DISPATCH_TRANSPORT",
            agent_id="A_ANALYTICS",
            args={
                "specimen_ids": ["S1"],
                "origin_site": "SITE_ACUTE",
                "dest_site": "SITE_HUB",
            },
            event_id="e0",
            t_s=10,
        )
    )
    assert disp["status"] == "ACCEPTED"
    cid = disp.get("consignment_id")
    assert cid
    ev = _event(
        "CHAIN_OF_CUSTODY_SIGN",
        agent_id="A_ANALYTICS",
        args={"consignment_id": cid},
        t_s=20,
    )
    return env, ev, "ACCEPTED"


HAPPY_OR_ILLEGAL: dict[str, HappyBuilder] = {
    "TICK": _happy_tick,
    "MOVE": _happy_move,
    "MINT_TOKEN": _happy_mint,
    "REVOKE_TOKEN": _happy_revoke,
    "OPEN_DOOR": _happy_open_door,
    "CENTRIFUGE_START": _happy_centrifuge_start,
    "QUEUE_RUN": _happy_queue_run,
    "CREATE_ACCESSION": _happy_create,
    "CHECK_ACCEPTANCE_RULES": _happy_check,
    "ACCEPT_SPECIMEN": _happy_accept,
    "HOLD_SPECIMEN": _happy_hold,
    "REJECT_SPECIMEN": _happy_reject,
    "CENTRIFUGE_END": _happy_centrifuge_end,
    "ALIQUOT_CREATE": _happy_aliquot,
    "START_RUN": _happy_start_run,
    "START_RUN_OVERRIDE": _happy_start_run_override,
    "QC_EVENT": _happy_qc_event,
    "GENERATE_RESULT": _happy_generate,
    "RELEASE_RESULT": _happy_release,
    "HOLD_RESULT": _happy_hold_result,
    "RERUN_REQUEST": _happy_rerun,
    "RELEASE_RESULT_OVERRIDE": _happy_release_override,
    "NOTIFY_CRITICAL_RESULT": _happy_notify,
    "ACK_CRITICAL_RESULT": _happy_ack,
    "ESCALATE_CRITICAL_RESULT": _happy_escalate,
    "DISPATCH_TRANSPORT": _happy_dispatch,
    "TRANSPORT_TICK": _happy_transport_tick,
    "RECEIVE_TRANSPORT": _happy_receive,
    "CHAIN_OF_CUSTODY_SIGN": _happy_coc,
}

# Documented illegal edges also counted as second coverage for OPEN_DOOR / ESCALATE
DOCUMENTED_ILLEGAL_EDGES: dict[str, HappyBuilder] = {
    "OPEN_DOOR": _illegal_open_door_documented,
    "ESCALATE_CRITICAL_RESULT": _illegal_escalate_documented,
}


def test_dispatch_tables_have_full_transition_coverage() -> None:
    missing_fail = sorted(DISPATCH_ACTIONS - set(PRECONDITION_FAIL))
    missing_happy = sorted(DISPATCH_ACTIONS - set(HAPPY_OR_ILLEGAL))
    assert not missing_fail, f"Missing precondition-fail cases: {missing_fail}"
    assert not missing_happy, f"Missing happy/illegal cases: {missing_happy}"
    unknown_fail = sorted(set(PRECONDITION_FAIL) - DISPATCH_ACTIONS)
    unknown_happy = sorted(set(HAPPY_OR_ILLEGAL) - DISPATCH_ACTIONS)
    assert not unknown_fail and not unknown_happy


@pytest.mark.parametrize("action_type", sorted(DISPATCH_ACTIONS))
def test_precondition_fail(action_type: str) -> None:
    env, event, expected_substr = PRECONDITION_FAIL[action_type]()
    before = _snapshot_world(env)
    out = env.step(event)
    assert out["status"] == "BLOCKED", (
        f"{action_type}: expected BLOCKED, got {out.get('status')} "
        f"reason={out.get('blocked_reason_code')}"
    )
    code = str(out.get("blocked_reason_code") or "")
    if expected_substr:
        assert expected_substr in code or code.endswith(expected_substr), (
            f"{action_type}: blocked_reason_code={code!r} expected to contain {expected_substr!r}"
        )
    after = _snapshot_world(env)
    # Specimens / agent zones must not change on BLOCKED (audit may grow).
    assert after["specimens"] == before["specimens"], f"{action_type} mutated specimens on BLOCKED"
    assert after["agent_zones"] == before["agent_zones"], f"{action_type} mutated zones on BLOCKED"


@pytest.mark.parametrize("action_type", sorted(DISPATCH_ACTIONS))
def test_happy_or_documented_illegal(action_type: str) -> None:
    env, event, expected_status = HAPPY_OR_ILLEGAL[action_type]()
    out = env.step(event)
    assert out["status"] == expected_status, (
        f"{action_type}: expected {expected_status}, got {out.get('status')} "
        f"reason={out.get('blocked_reason_code')} emits={out.get('emits')}"
    )
    if expected_status == "ACCEPTED":
        emits = out.get("emits") or []
        # TICK may accept with empty emits when no door alarms fire.
        if action_type == "TICK":
            return
        assert action_type in emits or "FORENSIC_FREEZE_LOG" in emits or emits, (
            f"{action_type}: empty emits on ACCEPTED: {out}"
        )


@pytest.mark.parametrize("action_type", sorted(DOCUMENTED_ILLEGAL_EDGES))
def test_documented_illegal_edge(action_type: str) -> None:
    env, event, expected_status = DOCUMENTED_ILLEGAL_EDGES[action_type]()
    out = env.step(event)
    assert out["status"] == expected_status


def test_blocked_hold_specimen_does_not_mutate() -> None:
    env = CoreEnv()
    _reset(env, _base_initial())
    assert env.query("specimen_status('S1')") == "arrived_at_reception"
    out = env.step(
        _event(
            "HOLD_SPECIMEN",
            agent_id="A_RECEPTION",
            args={"specimen_id": "S1"},
            reason_code=None,
        )
    )
    assert out["status"] == "BLOCKED"
    assert out.get("blocked_reason_code") == AUDIT_MISSING_REASON_CODE
    assert env.query("specimen_status('S1')") == "arrived_at_reception"


def test_blocked_rbac_does_not_mutate_specimen() -> None:
    env = CoreEnv()
    _reset(env, _base_initial())
    before = env.query("specimen_status('S1')")
    out = env.step(
        _event(
            "RELEASE_RESULT",
            agent_id="A_RECEPTION",
            args={"result_id": "RES_NOPE"},
        )
    )
    assert out["status"] == "BLOCKED"
    assert out.get("blocked_reason_code") == RBAC_ACTION_DENY
    assert env.query("specimen_status('S1')") == before
