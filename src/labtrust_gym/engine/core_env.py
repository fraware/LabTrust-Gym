"""
Core simulation engine: reset, step, and query.

This module implements the minimal engine that drives the lab simulation.
It handles reset (initial state), step (one tick with actions and
contract-shaped output), and query. Correctness is defined by golden
scenarios in policy/golden/golden_scenarios.v0.1.yaml; the IDs below
refer to those scenarios.

Behavior covered:
- Audit: append-only hash chain, optional fault injection for testing,
  forensic freeze when the chain is broken (scenario GS-022).
- Tokens: lifecycle, dual approval, replay protection (GS-010--013).
- Zones and doors: movement adjacency, OPEN_DOOR restrictions,
  door-open-too-long handling (GS-008, GS-009, GS-020).
- Reception: specimen acceptance, HOLD_SPECIMEN and reason codes
  (GS-003, GS-004, GS-005, GS-021).
- Quality control (QC): result gating, RELEASE_RESULT_OVERRIDE with
  drift token (GS-014, GS-015).

When the audit log is frozen (log_frozen), every step is BLOCKED with
blocked_reason_code AUDIT_CHAIN_BROKEN.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

from labtrust_gym.auth.authorize import is_tool_allowed as authz_is_tool_allowed
from labtrust_gym.baselines.llm.tool_proxy import get_tool_capabilities
from labtrust_gym.engine.audit_log import AuditLog
from labtrust_gym.engine.catalogue_runtime import (
    RC_REAGENT_STOCKOUT,
    build_initial_reagent_stock,
    check_stability,
    check_temp_out_of_band,
    get_panel_reagent_requirement,
    load_reagent_policy,
    load_stability_policy,
)
from labtrust_gym.engine.clock import Clock
from labtrust_gym.engine.critical import (
    CRIT_ACK_MISSING_FIELDS,
    CRIT_ESCALATION_OUT_OF_ORDER,
    CRIT_MODE_NOT_ALLOWED,
    CriticalStore,
    load_critical_thresholds,
    load_escalation_ladder,
)
from labtrust_gym.engine.devices import (
    DeviceStore,
    load_equipment_registry,
    load_failure_models,
)
from labtrust_gym.engine.enforcement import EnforcementEngine
from labtrust_gym.engine.invariants_runtime import (
    InvariantsRuntime,
    merge_violations_by_invariant_id,
)
from labtrust_gym.engine.qc import QCStore
from labtrust_gym.engine.queueing import PriorityClass, QueueStore
from labtrust_gym.engine.rbac import (
    RBAC_ACTION_DENY,
    check as rbac_check,
    get_agent_role as rbac_get_agent_role,
    get_allowed_actions as rbac_get_allowed_actions,
    load_rbac_policy as load_rbac_policy_path,
)
from labtrust_gym.engine.rng import RNG
from labtrust_gym.engine.signatures import (
    R_SYSTEM_CONTROL_ROLE,
    RUNTIME_CONTROL_ACTION_TYPES,
    SIG_MISSING,
    SIG_ROLE_MISMATCH,
    is_mutating_action,
    load_key_registry as load_key_registry_path,
    verify_action_signature,
)
from labtrust_gym.engine.specimens import SpecimenStore
from labtrust_gym.engine.tokens_runtime import TokenStore
from labtrust_gym.engine.transport import (
    TRANSPORT_CHAIN_OF_CUSTODY_BROKEN,
    TRANSPORT_ROUTE_FORBIDDEN,
    TRANSPORT_TEMP_EXCURSION,
    TransportStore,
    load_sites_policy,
)
from labtrust_gym.engine.zones import (
    ZoneState,
    build_device_zone_map,
    get_default_device_zone_map,
    load_zone_layout,
)
from labtrust_gym.policy.tokens import (
    load_token_registry,
    validate_dual_approval,
)
from labtrust_gym.engine.errors import (
    AUDIT_CHAIN_BROKEN,
    INV_TOK_001,
    RC_INJECT_SPECIMEN_DUPLICATE,
)
from labtrust_gym.engine.event import StepEventDict
from labtrust_gym.engine.policy_resolution import load_policy_or_effective
from labtrust_gym.engine.state import InitialStateDict
from labtrust_gym.engine.env_adapter import LabTrustEnvAdapter
from labtrust_gym.security.agent_capabilities import (
    check_capability,
    get_profile_for_agent,
    is_override_action,
    load_agent_capabilities,
)
from labtrust_gym.tools.arg_validation import (
    TOOL_ARG_RANGE_FAIL,
    TOOL_ARG_SCHEMA_FAIL,
    validate_tool_args,
)
from labtrust_gym.tools.capabilities import (
    get_allowed_capabilities_for_state,
    load_state_tool_capability_map,
)
from labtrust_gym.tools.execution import (
    TOOL_EXEC_EXCEPTION,
    execute_tool_safely,
)
from labtrust_gym.tools.registry import (
    check_tool_allowed,
)
from labtrust_gym.logging.step_timing import timed_step_method
from labtrust_gym.tools.sandbox import (
    ToolSandbox,
    load_tool_boundary_policy,
)

TOOL_SELECTION_ERROR = "TOOL_SELECTION_ERROR"
FORENSIC_FREEZE_LOG = "FORENSIC_FREEZE_LOG"
RBAC_RESTRICTED_ENTRY_DENY = "RBAC_RESTRICTED_ENTRY_DENY"
Z_RESTRICTED_BIOHAZARD = "Z_RESTRICTED_BIOHAZARD"
AUDIT_MISSING_REASON_CODE = "AUDIT_MISSING_REASON_CODE"
QC_FAIL_ACTIVE = "QC_FAIL_ACTIVE"
CRIT_NO_ACK = "CRIT_NO_ACK"
TIME_EXPIRED = "TIME_EXPIRED"
TEMP_OUT_OF_BAND = "TEMP_OUT_OF_BAND"
RC_DEVICE_NOT_COLOCATED = "RC_DEVICE_NOT_COLOCATED"
RC_DEVICE_UNKNOWN = "RC_DEVICE_UNKNOWN"
RC_QUEUE_BAD_PAYLOAD = "RC_QUEUE_BAD_PAYLOAD"
RC_QUEUE_DUPLICATE_WORK_ID = "RC_QUEUE_DUPLICATE_WORK_ID"
RC_QUEUE_EMPTY = "RC_QUEUE_EMPTY"
RC_QUEUE_HEAD_MISMATCH = "RC_QUEUE_HEAD_MISMATCH"
RC_DEVICE_BUSY = "RC_DEVICE_BUSY"
RC_DEVICE_MAINT = "RC_DEVICE_MAINT"
RC_DEVICE_FAULT = "RC_DEVICE_FAULT"

# Minimal token type config when policy file not found (GS-010 dual approval).
_DEFAULT_TOKEN_TYPES = {
    "OVERRIDE_RISK_ACCEPTANCE": {"approvals_required": 2, "ttl_s": 3600},
    "TOKEN_RESTRICTED_ENTRY": {"approvals_required": 1, "ttl_s": 900},
}

# Query dispatch: compiled patterns for parameterized queries (one match per expr).
_RE_QUERY_ZONE_STATE = re.compile(
    r"zone_state\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_DOOR_STATE = re.compile(
    r"door_state\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_SPECIMEN_STATUS = re.compile(
    r"specimen_status\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_LAST_REASON_CODE = re.compile(
    r"last_reason_code\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_RESULT_STATUS = re.compile(
    r"result_status\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_RESULT_FLAGS = re.compile(
    r"result_flags\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_RESULT_CRIT = re.compile(
    r"result_criticality\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_COMM_EXISTS = re.compile(
    r"comm_record_exists\s*\(\s*result_id\s*=\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_NOTIF_MODE = re.compile(
    r"notification_mode_required\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
)
_RE_QUERY_QUEUE_HEAD = re.compile(
    r"queue_head\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)"
)
_RE_QUERY_QUEUE_LENGTH = re.compile(
    r"queue_length\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)"
)
_RE_QUERY_AGENT_ZONE = re.compile(
    r"agent_zone\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)"
)
_RE_QUERY_DEVICE_QC = re.compile(
    r"device_qc_state\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)"
)
_RE_QUERY_DEVICE_STATE = re.compile(
    r"device_state\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)"
)

# Step dispatch: action_type -> handler method name. Handler takes (event, base), returns result dict.
# Early dispatch (before token_refs block): TICK, MOVE, MINT_TOKEN, REVOKE_TOKEN.
_STEP_DISPATCH: dict[str, str] = {
    "TICK": "_step_tick",
    "MOVE": "_step_move",
    "MINT_TOKEN": "_step_mint_token",
    "REVOKE_TOKEN": "_step_revoke_token",
}
# Late dispatch (after token_refs block): all other action types.
_STEP_DISPATCH_LATE: dict[str, str] = {
    "OPEN_DOOR": "_step_open_door",
    "CENTRIFUGE_START": "_step_centrifuge_start",
    "QUEUE_RUN": "_step_queue_run",
    "CREATE_ACCESSION": "_step_create_accession",
    "CHECK_ACCEPTANCE_RULES": "_step_check_acceptance_rules",
    "ACCEPT_SPECIMEN": "_step_accept_specimen",
    "HOLD_SPECIMEN": "_step_hold_specimen",
    "REJECT_SPECIMEN": "_step_reject_specimen",
    "CENTRIFUGE_END": "_step_centrifuge_end",
    "ALIQUOT_CREATE": "_step_aliquot_create",
    "START_RUN": "_step_start_run",
    "START_RUN_OVERRIDE": "_step_start_run_override",
    "QC_EVENT": "_step_qc_event",
    "GENERATE_RESULT": "_step_generate_result",
    "RELEASE_RESULT": "_step_release_result",
    "HOLD_RESULT": "_step_hold_result",
    "RERUN_REQUEST": "_step_rerun_request",
    "RELEASE_RESULT_OVERRIDE": "_step_release_result_override",
    "NOTIFY_CRITICAL_RESULT": "_step_notify_critical_result",
    "ACK_CRITICAL_RESULT": "_step_ack_critical_result",
    "ESCALATE_CRITICAL_RESULT": "_step_escalate_critical_result",
    "DISPATCH_TRANSPORT": "_step_dispatch_transport",
    "TRANSPORT_TICK": "_step_transport_tick",
    "RECEIVE_TRANSPORT": "_step_receive_transport",
    "CHAIN_OF_CUSTODY_SIGN": "_step_chain_of_custody_sign",
}


class CoreEnv(LabTrustEnvAdapter):
    """
    Minimal engine: audit log, token store, forensic freeze, contract step output.
    Implements LabTrustEnvAdapter for the golden runner.
    """

    def __init__(self) -> None:
        self._audit: AuditLog | None = None
        self._system_state: dict[str, Any] = {}
        self._tokens: TokenStore = TokenStore()
        self._token_registry: dict[str, Any] = {}
        self._zones: ZoneState | None = None
        self._device_zone: dict[str, str] = {}
        self._specimens: SpecimenStore | None = None
        self._qc: QCStore | None = None
        self._critical: CriticalStore | None = None
        self._queues: QueueStore | None = None
        self._now_ts: int = 0
        self._invariants_runtime: InvariantsRuntime | None = None
        self._enforcement_engine: EnforcementEngine | None = None
        self._enforcement_enabled: bool = False
        self._transport: TransportStore | None = None
        self._transport_fault_injection: dict[str, Any] = {}
        self._key_registry: dict[str, Any] = {}
        self._strict_signatures: bool = False
        self._partner_id: str | None = None
        self._policy_fingerprint: str | None = None
        self._rbac_policy: dict[str, Any] = {}
        self._capability_policy: dict[str, Any] = {}
        self._episode_agent_action_count: dict[str, int] = {}
        self._episode_agent_override_count: dict[str, int] = {}

    def reset(
        self,
        initial_state: InitialStateDict | dict[str, Any],
        *,
        deterministic: bool,
        rng_seed: int,
    ) -> None:
        fault_injection = initial_state.get("audit_fault_injection")
        self._audit = AuditLog(fault_injection=fault_injection)
        system = initial_state.get("system") or {}
        self._system_state = {
            "log_frozen": False,
            "last_reason_code_system": None,
            "downtime_active": bool(system.get("downtime_active", False)),
        }
        self._tokens = TokenStore()
        self._tokens.load_initial(initial_state.get("tokens", []))
        self._now_ts = 0
        path = Path("policy/tokens/token_registry.v0.1.yaml")
        if path.exists():
            try:
                self._token_registry = load_token_registry(path)
            except Exception:
                self._token_registry = {"token_types": _DEFAULT_TOKEN_TYPES}
        else:
            self._token_registry = {"token_types": _DEFAULT_TOKEN_TYPES}
        effective_policy_early = initial_state.get("effective_policy")
        zone_layout_inline = (effective_policy_early or {}).get(
            "zone_layout"
        ) or initial_state.get("zone_layout")
        if zone_layout_inline and isinstance(zone_layout_inline, dict):
            layout = zone_layout_inline
            self._zones = ZoneState(layout)
            self._device_zone = build_device_zone_map(
                layout.get("device_placement", [])
            )
        else:
            zone_path = Path("policy/zones/zone_layout_policy.v0.1.yaml")
            if zone_path.exists():
                try:
                    layout = load_zone_layout(zone_path)
                    self._zones = ZoneState(layout)
                    self._device_zone = build_device_zone_map(
                        layout.get("device_placement", [])
                    )
                except Exception:
                    self._zones = ZoneState(None)
                    self._device_zone = get_default_device_zone_map()
            else:
                self._zones = ZoneState(None)
                self._device_zone = get_default_device_zone_map()
        self._emit_scale_config_at_step = bool(
            initial_state.get("_scale_config_sanitized") is not None
        )
        agents = initial_state.get("agents")
        if isinstance(agents, list):
            agent_positions = {}
            for a in agents:
                if isinstance(a, dict) and a.get("agent_id") and a.get("zone_id"):
                    agent_positions[str(a["agent_id"])] = str(a["zone_id"])
            if agent_positions:
                self._zones.reset(agent_positions)
        else:
            self._zones.reset(None)
        self._specimens = SpecimenStore()
        self._specimens.load_initial(initial_state.get("specimens", []))
        self._qc = QCStore()
        self._critical = CriticalStore()
        effective_policy = initial_state.get("effective_policy")
        from labtrust_gym.engine.critical import default_thresholds

        th = default_thresholds()
        if effective_policy and isinstance(
            effective_policy.get("critical_thresholds"), list
        ):
            th = effective_policy["critical_thresholds"]
        else:
            crit_path = Path("policy/critical/critical_thresholds.v0.1.yaml")
            if crit_path.exists():
                try:
                    th = load_critical_thresholds(crit_path)
                except Exception:
                    pass
        self._critical.load_thresholds(th)
        ladder = None
        if effective_policy and isinstance(
            effective_policy.get("escalation_ladder"), dict
        ):
            ladder = effective_policy["escalation_ladder"]
        else:
            ladder = load_escalation_ladder()
        self._critical.load_ladder(ladder)
        self._queues = QueueStore()
        self._queues.set_known_devices(list(self._device_zone.keys()))
        self._timing_mode = (
            str(initial_state.get("timing_mode", "explicit")).strip().lower()
        )
        if self._timing_mode not in ("explicit", "simulated"):
            self._timing_mode = "explicit"
        self._clock = None
        self._device_store = None
        self._rng = None
        if self._timing_mode == "simulated":
            self._rng = RNG(rng_seed)
            if effective_policy and isinstance(
                effective_policy.get("equipment_registry"), dict
            ):
                registry = effective_policy["equipment_registry"]
            else:
                registry = load_equipment_registry()
            failure_models = None
            policy_root_for_fm = initial_state.get("policy_root")
            root_path = Path(policy_root_for_fm) if policy_root_for_fm else Path(".")
            fm_path = root_path / "policy" / "equipment" / "failure_models.v0.1.yaml"
            if fm_path.exists():
                failure_models = load_failure_models(fm_path)
            self._device_store = DeviceStore(
                registry=registry, rng=self._rng, failure_models=failure_models
            )
            self._device_store.set_known_devices(list(self._device_zone.keys()))
            self._clock = Clock()
        self._stability_policy: dict[str, Any] = {}
        if effective_policy and isinstance(
            effective_policy.get("stability_policy"), dict
        ):
            self._stability_policy = effective_policy["stability_policy"]
        else:
            stab_path = Path("policy/stability/stability_policy.v0.1.yaml")
            if stab_path.exists():
                try:
                    self._stability_policy = load_stability_policy(stab_path)
                except Exception:
                    pass
        _root_inv = initial_state.get("policy_root")
        _inv_root = Path(_root_inv) if _root_inv else Path(".")
        inv_path = _inv_root / "policy" / "invariants" / "invariant_registry.v1.0.yaml"
        if inv_path.exists():
            try:
                self._invariants_runtime = InvariantsRuntime(inv_path)
            except Exception:
                self._invariants_runtime = None
        else:
            self._invariants_runtime = None
        self._reagent_policy = {}
        self._reagent_stock = {}
        _root = initial_state.get("policy_root")
        _rp_root = Path(_root) if _root else Path(".")
        rp_path = _rp_root / "policy" / "reagents" / "reagent_policy.v0.1.yaml"
        if rp_path.exists():
            self._reagent_policy = load_reagent_policy(rp_path)
            self._reagent_stock = build_initial_reagent_stock(self._reagent_policy)
        override = initial_state.get("reagent_initial_stock")
        if isinstance(override, dict):
            for k, v in override.items():
                if isinstance(v, int | float):
                    self._reagent_stock[str(k)] = float(v)
        self._enforcement_enabled = bool(
            initial_state.get("enforcement_enabled", False)
        )
        self._transport = TransportStore()
        self._transport_fault_injection = (
            initial_state.get("transport_fault_injection") or {}
        )
        sites_policy = load_sites_policy(Path("policy/sites/sites_policy.v0.1.yaml"))
        if effective_policy and isinstance(effective_policy.get("sites_policy"), dict):
            sites_policy = effective_policy["sites_policy"]
        self._transport.load_policy(sites_policy)
        if self._rng is not None:
            self._transport.set_rng(self._rng)
        if self._enforcement_enabled:
            if effective_policy and isinstance(
                effective_policy.get("enforcement_map"), dict
            ):
                self._enforcement_engine = EnforcementEngine(
                    map_data=effective_policy["enforcement_map"]
                )
                self._enforcement_engine.reset_counts()
            else:
                enf_path = Path("policy/enforcement/enforcement_map.v0.1.yaml")
                if enf_path.exists():
                    try:
                        self._enforcement_engine = EnforcementEngine(enf_path)
                        self._enforcement_engine.reset_counts()
                    except Exception:
                        self._enforcement_engine = None
                else:
                    self._enforcement_engine = None
        else:
            self._enforcement_engine = None
        # Key registry for signed actions
        _policy_root_for_resolution = initial_state.get("policy_root")
        key_registry_raw = load_policy_or_effective(
            effective_policy,
            "key_registry",
            _policy_root_for_resolution,
            "policy/keys/key_registry.v0.1.yaml",
            load_key_registry_path,
            {"version": "0.1", "keys": []},
        )
        self._key_registry = {
            "version": key_registry_raw.get("version", "0.1"),
            "keys": list(key_registry_raw.get("keys") or []),
        }
        import os

        self._strict_signatures = bool(
            initial_state.get("strict_signatures")
            or os.environ.get("LABTRUST_STRICT_SIGNATURES") == "1"
        )
        self._partner_id = initial_state.get("partner_id")
        self._policy_fingerprint = initial_state.get("policy_fingerprint")
        rbac_raw = load_policy_or_effective(
            effective_policy,
            "rbac_policy",
            _policy_root_for_resolution,
            "policy/rbac/rbac_policy.v0.1.yaml",
            load_rbac_policy_path,
            {},
        )
        self._rbac_policy = {
            "version": rbac_raw.get("version", "0.1"),
            "roles": dict(rbac_raw.get("roles") or {}),
            "agents": dict(rbac_raw.get("agents") or {}),
            "action_constraints": dict(rbac_raw.get("action_constraints") or {}),
        }
        if effective_policy and isinstance(
            effective_policy.get("agent_capabilities"), dict
        ):
            self._capability_policy = dict(effective_policy["agent_capabilities"])
        else:
            self._capability_policy = load_agent_capabilities(Path("."))
        self._episode_agent_action_count = {}
        self._episode_agent_override_count = {}
        self._tool_registry: dict[str, Any] = dict(
            initial_state.get("tool_registry") or {}
        )
        self._allowed_tools: list[str] | None = initial_state.get("allowed_tools")
        _policy_root = initial_state.get("policy_root")
        self._policy_root: Path | None = (
            Path(_policy_root) if _policy_root is not None else None
        )
        self._tool_adapter: Any | None = initial_state.get("tool_adapter")
        self._tool_timeout_s: float | None = initial_state.get("tool_timeout_s")
        self._state_label: str | None = initial_state.get("state_label")
        state_map = initial_state.get("state_tool_capability_map")
        if state_map is not None and isinstance(state_map, dict):
            self._state_tool_capability_map = dict(state_map)
        elif self._policy_root is not None:
            self._state_tool_capability_map = load_state_tool_capability_map(
                self._policy_root
            )
        else:
            self._state_tool_capability_map = {}
        self._tool_boundary_policy: dict[str, Any] = {}
        if self._policy_root is not None and self._tool_registry:
            self._tool_boundary_policy = load_tool_boundary_policy(self._policy_root)

    def _increment_capability_counts(self, agent_id: str, action_type: str) -> None:
        """Increment per-episode action and override counts (after ACCEPTED)."""
        if not agent_id:
            return
        self._episode_agent_action_count[agent_id] = (
            self._episode_agent_action_count.get(agent_id, 0) + 1
        )
        if self._capability_policy and is_override_action(
            action_type, self._capability_policy
        ):
            self._episode_agent_override_count[agent_id] = (
                self._episode_agent_override_count.get(agent_id, 0) + 1
            )

    def _blocked_result(
        self,
        base: dict[str, Any],
        reason_code: str,
        hashchain_snap: dict[str, Any],
        *,
        emits: list[str] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Build step result dict for BLOCKED status. Caller must pass hashchain snapshot."""
        out: dict[str, Any] = {
            **base,
            "status": "BLOCKED",
            "emits": list(emits) if emits is not None else list(base.get("emits", [])),
            "blocked_reason_code": reason_code,
            "hashchain": hashchain_snap,
        }
        out.update(extra)
        return out

    def _accepted_result(
        self,
        base: dict[str, Any],
        emits: list[str],
        hashchain_dict: dict[str, Any],
        **extra: Any,
    ) -> dict[str, Any]:
        """Build step result dict for ACCEPTED status. Caller must pass hashchain from audit.append."""
        out: dict[str, Any] = {
            **base,
            "status": "ACCEPTED",
            "emits": list(emits),
            "blocked_reason_code": None,
            "hashchain": hashchain_dict,
        }
        out.update(extra)
        return out

    def _finalize_step(
        self, event: StepEventDict | dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge registry invariant violations; optionally apply enforcement and record to audit."""
        if getattr(self, "_emit_scale_config_at_step", False):
            result = dict(result)
            result["emits"] = list(result.get("emits", [])) + ["COORD_SCALE_CONFIG"]
            self._emit_scale_config_at_step = False
        if result.get("status") != "ACCEPTED":
            return result
        self._increment_capability_counts(
            str(event.get("agent_id", "")),
            str(event.get("action_type", "")),
        )
        if self._invariants_runtime is not None:
            legacy = result.get("violations") or []
            registry = self._invariants_runtime.evaluate(self, event, result)
            result = {
                **result,
                "violations": merge_violations_by_invariant_id(legacy, registry),
            }
        enforcements: list[dict[str, Any]] = result.get("enforcements") or []
        if (
            self._enforcement_enabled
            and self._enforcement_engine
            and self._audit is not None
        ):
            violations = result.get("violations") or []
            from labtrust_gym.control_plane import apply_enforcement_post_step

            enforcements = apply_enforcement_post_step(
                event,
                violations,
                self._enforcement_engine,
                audit_callback=None,
            )
            for i, enf in enumerate(enforcements):
                self._audit.append(
                    {
                        "event_id": f"{event.get('event_id', 'step')}_enf_{i}",
                        "event_type": "ENFORCEMENT",
                        "rule_id": enf.get("rule_id"),
                        "action_type": enf.get("type"),
                        "target": enf.get("target"),
                        "duration_s": enf.get("duration_s"),
                        "reason_code": enf.get("reason_code"),
                        "zone_id": enf.get("zone_id"),
                    }
                )
        result = {**result, "enforcements": enforcements}
        if getattr(self, "_step_signature_verification", None) is not None:
            result["signature_verification"] = self._step_signature_verification
        return result

    def _step_tick(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        t_s = int(event.get("t_s", 0))
        violations, emits = self._zones.tick(t_s)
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._finalize_step(
                event,
                {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "violations": violations,
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                },
            )
        return self._finalize_step(
            event,
            {
                **base,
                "status": "ACCEPTED",
                "emits": emits if emits else [],
                "violations": violations,
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            },
        )

    def _step_move(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        args = event.get("args", {})
        token_refs = event.get("token_refs", [])
        from_zone = str(args.get("from_zone", ""))
        to_zone = str(args.get("to_zone", ""))
        entity_type = args.get("entity_type", "Agent")
        agent_id = str(event.get("agent_id", ""))
        t_s = int(event.get("t_s", 0))
        if entity_type == "Specimen":
            ok = self._zones.is_adjacent(from_zone, to_zone)
            move_violations = (
                []
                if ok
                else [{"invariant_id": "INV-ZONE-001", "status": "VIOLATION"}]
            )
            blocked_code = None if ok else "RC_ILLEGAL_MOVE"
        else:
            if not agent_id:
                agent_id = str(args.get("entity_id", event.get("agent_id", "")))
            ok, move_violations, blocked_code = self._zones.move(
                agent_id, from_zone, to_zone
            )
        if not ok:
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(
                base, blocked_code, hashchain_dict,
                violations=move_violations,
            )
        if to_zone == Z_RESTRICTED_BIOHAZARD:
            if not token_refs:
                hashchain_dict, _ = self._audit.append(event)
                return self._blocked_result(
                    base, RBAC_RESTRICTED_ENTRY_DENY, hashchain_dict,
                    violations=[
                        {"invariant_id": "INV-ZONE-004", "status": "VIOLATION"},
                        {"invariant_id": "INV-TOK-003", "status": "VIOLATION"},
                    ],
                )
            for tid in token_refs:
                v = self._tokens.validity_violation(tid, t_s)
                if v:
                    hashchain_dict, _ = self._audit.append(event)
                    return self._blocked_result(
                        base, RBAC_RESTRICTED_ENTRY_DENY, hashchain_dict,
                        violations=[{"invariant_id": v, "status": "VIOLATION"}],
                    )
            for tid in token_refs:
                self._tokens.consume_token(tid)
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return self._accepted_result(
                    base, [FORENSIC_FREEZE_LOG], hashchain_dict,
                    token_consumed=list(token_refs),
                )
            return self._accepted_result(
                base, ["MOVE"], hashchain_dict,
                token_consumed=list(token_refs),
            )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["MOVE"], hashchain_dict)

    def _step_mint_token(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        approvals = args.get("approvals", [])
        if not (isinstance(approvals, list) and approvals):
            approvals = []
        token_type = args.get("token_type", "")
        ok, dual_approval_violation = validate_dual_approval(
            approvals, token_type, self._token_registry
        )
        if not ok and dual_approval_violation:
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(
                base, dual_approval_violation or "", hashchain_dict,
                violations=[
                    {"invariant_id": dual_approval_violation or "", "status": "VIOLATION"},
                ],
            )
        subject_type = args.get("subject_type", "")
        subject_id = args.get("subject_id", "")
        reason_code = args.get("reason_code")
        token_types = self._token_registry.get("token_types") or _DEFAULT_TOKEN_TYPES
        meta = token_types.get(token_type, {})
        ttl_s = int(meta.get("ttl_s", 3600))
        token_id = (
            f"T_OVR_{subject_id}"
            if "OVERRIDE" in token_type
            else f"T_{token_type}_{subject_id}"
        )
        try:
            self._tokens.mint_token(
                token_id=token_id,
                token_type=token_type,
                subject_type=subject_type,
                subject_id=subject_id,
                issued_at_ts_s=t_s,
                expires_at_ts_s=t_s + ttl_s,
                reason_code=reason_code,
                approvals=approvals,
            )
        except ValueError:
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(
                base, INV_TOK_001, hashchain_dict,
                violations=[{"invariant_id": INV_TOK_001, "status": "VIOLATION"}],
            )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["MINT_TOKEN"], hashchain_dict)

    def _step_revoke_token(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        args = event.get("args", {})
        token_id = args.get("token_id")
        if token_id:
            self._tokens.revoke_token(token_id)
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["REVOKE_TOKEN"], hashchain_dict)

    def _step_default(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        action_type = event.get("action_type", "")
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        default_emits = list(base.get("emits", []))
        if action_type:
            default_emits.append(action_type)
        return self._accepted_result(base, default_emits, hashchain_dict)

    def _step_open_door(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        args = event.get("args", {})
        token_refs = event.get("token_refs", [])
        t_s = int(event.get("t_s", 0))
        if args.get("door_id") == "D_RESTRICTED_AIRLOCK" and not token_refs:
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(
                base, RBAC_RESTRICTED_ENTRY_DENY, hashchain_dict,
                violations=[
                    {"invariant_id": "INV-ZONE-004", "status": "VIOLATION"},
                    {"invariant_id": "INV-TOK-003", "status": "VIOLATION"},
                ],
            )
        door_id = args.get("door_id", "")
        if door_id and self._zones is not None:
            self._zones.open_door(door_id, t_s)
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["OPEN_DOOR"], hashchain_dict)

    def _step_centrifuge_start(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        args = event.get("args", {})
        t_s = int(event.get("t_s", 0))
        device_id = args.get("device_id")
        agent_id = str(event.get("agent_id", ""))
        violations_list: list[dict[str, Any]] = []
        if device_id and self._zones is not None:
            device_zone = self._device_zone.get(str(device_id))
            agent_zone = self._zones.get_agent_zone(agent_id) if agent_id else None
            if device_zone and agent_zone is not None and agent_zone != device_zone:
                hashchain_dict, _ = self._audit.append(event)
                return self._blocked_result(
                    base, RC_DEVICE_NOT_COLOCATED, hashchain_dict,
                    violations=[{"invariant_id": "INV-ZONE-002", "status": "VIOLATION"}],
                )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._finalize_step(
                event,
                {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "violations": violations_list,
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                },
            )
        return self._finalize_step(
            event,
            {
                **base,
                "status": "ACCEPTED",
                "emits": ["CENTRIFUGE_START"],
                "violations": violations_list,
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            },
        )

    def _step_queue_run(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._queues is not None and self._zones is not None
        args = event.get("args", {})
        t_s = int(event.get("t_s", 0))
        device_id = args.get("device_id")
        work_id = args.get("work_id") or args.get("specimen_id")
        if not work_id and args.get("accession_ids"):
            ids = args["accession_ids"]
            work_id = ids[0] if isinstance(ids, list) and ids else None
        if not work_id and args.get("aliquot_ids") and self._specimens is not None:
            resolved = self._specimens.resolve_to_specimen_ids(
                None, args.get("aliquot_ids")
            )
            work_id = resolved[0] if resolved else None
        if not work_id and args.get("aliquot_ids"):
            ids = args["aliquot_ids"]
            work_id = ids[0] if isinstance(ids, list) and ids else None
        priority_raw = (
            args.get("priority") or args.get("priority_class") or "ROUTINE"
        )
        priority_class = (
            str(priority_raw).upper()
            if str(priority_raw).upper() in ("STAT", "URGENT", "ROUTINE")
            else "ROUTINE"
        )
        if not device_id or not work_id:
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(base, RC_QUEUE_BAD_PAYLOAD, hashchain_dict)
        if not self._queues.is_known_device(str(device_id)):
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(base, RC_DEVICE_UNKNOWN, hashchain_dict)
        agent_id = str(event.get("agent_id", ""))
        if device_id and self._device_zone.get(str(device_id)) and agent_id:
            device_zone = self._device_zone.get(str(device_id))
            agent_zone = self._zones.get_agent_zone(agent_id)
            if agent_zone is not None and device_zone != agent_zone:
                hashchain_dict, _ = self._audit.append(event)
                return self._blocked_result(
                    base, RC_DEVICE_NOT_COLOCATED, hashchain_dict,
                    violations=[{"invariant_id": "INV-ZONE-002", "status": "VIOLATION"}],
                )
        ok = self._queues.enqueue(
            str(device_id),
            str(work_id),
            cast(PriorityClass, priority_class),
            t_s,
            agent_id,
            event.get("reason_code") or args.get("reason_code"),
            allow_duplicate_work_id=True,
        )
        if not ok:
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(base, RC_QUEUE_DUPLICATE_WORK_ID, hashchain_dict)
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["QUEUE_RUN"], hashchain_dict)

    def _step_create_accession(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._specimens is not None
        args = event.get("args", {})
        specimen_id = args.get("specimen_id")
        if specimen_id and self._specimens.create_accession(str(specimen_id)):
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
            return self._accepted_result(base, ["CREATE_ACCESSION"], hashchain_dict)
        return self._step_default(event, base)

    def _step_check_acceptance_rules(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._specimens is not None
        args = event.get("args", {})
        specimen_id = args.get("specimen_id")
        id_match = args.get("id_match")
        if specimen_id:
            self._specimens.check_acceptance_rules(str(specimen_id), id_match)
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["CHECK_ACCEPTANCE_RULES"], hashchain_dict)

    def _step_accept_specimen(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._specimens is not None
        args = event.get("args", {})
        specimen_id = args.get("specimen_id")
        if specimen_id:
            outcome, emits, blocked_code, _ = self._specimens.accept_specimen(
                str(specimen_id)
            )
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return self._finalize_step(
                    event,
                    {
                        **base,
                        "status": "ACCEPTED",
                        "emits": [FORENSIC_FREEZE_LOG],
                        "blocked_reason_code": None,
                        "violations": [],
                        "hashchain": hashchain_dict,
                    },
                )
            return self._finalize_step(
                event,
                {
                    **base,
                    "status": outcome,
                    "emits": emits,
                    "blocked_reason_code": blocked_code,
                    "violations": [],
                    "hashchain": hashchain_dict,
                },
            )
        return self._step_default(event, base)

    def _step_hold_specimen(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._specimens is not None
        args = event.get("args", {})
        reason_code = event.get("reason_code") or args.get("reason_code")
        specimen_id = args.get("specimen_id")
        if not specimen_id:
            hashchain_dict, _ = self._audit.append(event)
            return self._accepted_result(base, ["HOLD_SPECIMEN"], hashchain_dict)
        ok, blocked_code = self._specimens.hold_specimen(
            str(specimen_id), reason_code
        )
        if not ok and blocked_code == AUDIT_MISSING_REASON_CODE:
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(base, AUDIT_MISSING_REASON_CODE, hashchain_dict)
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["HOLD_SPECIMEN"], hashchain_dict)

    def _step_reject_specimen(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._specimens is not None
        args = event.get("args", {})
        specimen_id = args.get("specimen_id")
        reason_code = event.get("reason_code") or args.get("reason_code")
        if specimen_id and self._specimens.reject_specimen(
            str(specimen_id), reason_code
        ):
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
            return self._accepted_result(base, ["REJECT_SPECIMEN"], hashchain_dict)
        return self._step_default(event, base)

    def _step_centrifuge_end(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._specimens is not None
        args = event.get("args", {})
        t_s = int(event.get("t_s", 0))
        specimen_ids = args.get("specimen_ids") or []
        separated_ts_s = args.get("separated_ts_s", t_s)
        for sid in specimen_ids:
            self._specimens.set_separated_ts(str(sid), int(separated_ts_s))
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["CENTRIFUGE_END"], hashchain_dict)

    def _step_aliquot_create(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._specimens is not None
        args = event.get("args", {})
        specimen_id = args.get("specimen_id")
        aliquot_id = args.get("aliquot_id")
        if specimen_id and aliquot_id:
            self._specimens.record_aliquot(str(aliquot_id), str(specimen_id))
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["ALIQUOT_CREATE"], hashchain_dict)

    def _step_start_run(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._qc is not None and self._specimens is not None
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        token_refs = event.get("token_refs", [])
        device_id = args.get("device_id")
        agent_id = str(event.get("agent_id", ""))
        if device_id and self._zones is not None:
            device_zone = self._device_zone.get(str(device_id))
            agent_zone = self._zones.get_agent_zone(agent_id) if agent_id else None
            if device_zone and agent_zone is not None and agent_zone != device_zone:
                hashchain_dict, _ = self._audit.append(event)
                return self._blocked_result(
                    base, RC_DEVICE_NOT_COLOCATED, hashchain_dict,
                    violations=[{"invariant_id": "INV-ZONE-002", "status": "VIOLATION"}],
                )
        if (
            self._timing_mode == "simulated"
            and self._device_store is not None
            and device_id
            and not self._device_store.can_start_run(str(device_id))
        ):
            block_reason = self._device_store.device_block_reason(str(device_id))
            reason_code = (
                RC_DEVICE_MAINT
                if block_reason == "MAINT"
                else RC_DEVICE_FAULT if block_reason == "FAULT" else RC_DEVICE_BUSY
            )
            hashchain_dict, _ = self._audit.append(event)
            return self._blocked_result(base, reason_code, hashchain_dict)
        resolved_specimen_ids: list[str] | None = None
        if self._queues is not None and device_id:
            resolved_from_args = self._specimens.resolve_to_specimen_ids(
                args.get("specimen_ids"),
                args.get("aliquot_ids"),
            )
            explicit_work_id = args.get("work_id")
            if not resolved_from_args and not explicit_work_id:
                work_id_from_queue = self._queues.consume_head(str(device_id))
                if work_id_from_queue is None:
                    hashchain_dict, _ = self._audit.append(event)
                    return self._blocked_result(base, RC_QUEUE_EMPTY, hashchain_dict)
                resolved_specimen_ids = [work_id_from_queue]
            elif resolved_from_args or explicit_work_id:
                work_id = explicit_work_id or (
                    resolved_from_args[0] if resolved_from_args else None
                )
                if work_id is not None:
                    head = self._queues.queue_head(str(device_id))
                    if head is not None and head != str(work_id):
                        hashchain_dict, _ = self._audit.append(event)
                        return self._blocked_result(
                            base, RC_QUEUE_HEAD_MISMATCH, hashchain_dict,
                        )
                    if head == str(work_id):
                        self._queues.consume_head(str(device_id))
                resolved_specimen_ids = resolved_from_args or (
                    [str(explicit_work_id)] if explicit_work_id else []
                )
        if resolved_specimen_ids is None:
            resolved_specimen_ids = self._specimens.resolve_to_specimen_ids(
                args.get("specimen_ids"),
                args.get("aliquot_ids"),
            )
        start_violations: list[dict[str, Any]] = []
        for sid in resolved_specimen_ids or []:
            specimen_rec = self._specimens.get(sid)
            if not specimen_rec:
                continue
            panel_id = specimen_rec.get("panel_id") or "BIOCHEM_PANEL_CORE"
            collection_ts_s = int(specimen_rec.get("collection_ts_s", 0))
            separated_ts_s = specimen_rec.get("separated_ts_s")
            if separated_ts_s is not None:
                separated_ts_s = int(separated_ts_s)
            temp_band = specimen_rec.get("temp_band") or "AMBIENT_20_25"
            ok, viol_id, reason, _ = check_stability(
                collection_ts_s,
                separated_ts_s,
                t_s,
                panel_id,
                self._stability_policy,
                temp_band,
            )
            if not ok and not token_refs:
                hashchain_dict, _ = self._audit.append(event)
                return self._blocked_result(
                    base, reason or TIME_EXPIRED, hashchain_dict,
                    violations=[{"invariant_id": viol_id, "status": "VIOLATION"}],
                )
            if (
                check_temp_out_of_band(
                    specimen_rec.get("storage_requirement"),
                    specimen_rec.get("temp_exposure_log"),
                )
                and not token_refs
            ):
                hashchain_dict, _ = self._audit.append(event)
                return self._blocked_result(
                    base, TEMP_OUT_OF_BAND, hashchain_dict,
                    violations=[{"invariant_id": "INV-ZONE-006", "status": "VIOLATION"}],
                )
        first_panel_id = None
        if resolved_specimen_ids and self._specimens:
            first_spec = (
                self._specimens.get(resolved_specimen_ids[0])
                if resolved_specimen_ids
                else None
            )
            first_panel_id = first_spec.get("panel_id") if first_spec else None
        if self._reagent_policy and first_panel_id:
            req = get_panel_reagent_requirement(
                self._reagent_policy, first_panel_id
            )
            if req is not None:
                reagent_id, qty, _ = req
                current = self._reagent_stock.get(reagent_id, 0.0)
                if current < qty:
                    hashchain_dict, _ = self._audit.append(event)
                    return self._blocked_result(
                        base, RC_REAGENT_STOCKOUT, hashchain_dict,
                    )
        device_id = args.get("device_id")
        run_id = args.get("run_id")
        if device_id and run_id:
            self._qc.register_run(str(run_id), str(device_id))
        if self._reagent_policy and first_panel_id:
            req = get_panel_reagent_requirement(
                self._reagent_policy, first_panel_id
            )
            if req is not None:
                reagent_id, qty, _ = req
                self._reagent_stock[reagent_id] = (
                    self._reagent_stock.get(reagent_id, 0.0) - qty
                )
        if (
            self._timing_mode == "simulated"
            and self._device_store is not None
            and device_id
            and run_id
        ):
            self._device_store.start_run(
                str(device_id),
                str(run_id),
                t_s,
                work_id=resolved_specimen_ids[0] if resolved_specimen_ids else None,
                specimen_ids=resolved_specimen_ids or [],
                panel_id=first_panel_id,
            )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._finalize_step(
                event,
                {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "violations": start_violations,
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                },
            )
        return self._finalize_step(
            event,
            {
                **base,
                "status": "ACCEPTED",
                "emits": ["START_RUN"],
                "violations": start_violations,
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            },
        )

    def _step_start_run_override(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._specimens is not None and self._qc is not None
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        token_refs = event.get("token_refs", [])
        device_id = args.get("device_id")
        agent_id = str(event.get("agent_id", ""))
        if device_id and self._zones is not None:
            device_zone = self._device_zone.get(str(device_id))
            agent_zone = self._zones.get_agent_zone(agent_id) if agent_id else None
            if device_zone and agent_zone is not None and agent_zone != device_zone:
                hashchain_dict, _ = self._audit.append(event)
                return self._blocked_result(
                    base, RC_DEVICE_NOT_COLOCATED, hashchain_dict,
                    violations=[{"invariant_id": "INV-ZONE-002", "status": "VIOLATION"}],
                )
        specimen_ids = self._specimens.resolve_to_specimen_ids(
            args.get("specimen_ids"),
            args.get("aliquot_ids"),
        )
        if specimen_ids and token_refs:
            for tid in token_refs:
                v = self._tokens.validity_violation(tid, t_s)
                if v:
                    hashchain_dict, _ = self._audit.append(event)
                    return self._blocked_result(
                        base, TIME_EXPIRED, hashchain_dict,
                        violations=[{"invariant_id": v, "status": "VIOLATION"}],
                    )
            for tid in token_refs:
                self._tokens.consume_token(tid)
            device_id = args.get("device_id")
            run_id = args.get("run_id")
            if device_id and run_id:
                self._qc.register_run(str(run_id), str(device_id))
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._finalize_step(
                event,
                {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "token_consumed": (
                        list(token_refs) if specimen_ids and token_refs else []
                    ),
                    "violations": [],
                    "hashchain": hashchain_dict,
                },
            )
        return self._finalize_step(
            event,
            {
                **base,
                "status": "ACCEPTED",
                "emits": ["START_RUN"],
                "blocked_reason_code": None,
                "token_consumed": (
                    list(token_refs) if specimen_ids and token_refs else []
                ),
                "violations": [],
                "hashchain": hashchain_dict,
            },
        )

    def _step_qc_event(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._qc is not None
        args = event.get("args", {})
        device_id = args.get("device_id")
        qc_outcome = args.get("qc_outcome", "pass")
        if device_id:
            self._qc.set_device_qc_state(str(device_id), str(qc_outcome))
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["QC_EVENT"], hashchain_dict)

    def _step_generate_result(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._qc is not None
        args = event.get("args", {})
        result_id = args.get("result_id")
        run_id = args.get("run_id")
        device_id = args.get("device_id")
        qc_state = args.get("qc_state")
        analyte_code = args.get("analyte_code")
        value = args.get("value")
        units = args.get("units", "")
        if result_id:
            self._qc.create_result(
                str(result_id),
                str(run_id) if run_id else None,
                device_id=str(device_id) if device_id else None,
                qc_state=str(qc_state) if qc_state else None,
            )
            if (
                analyte_code is not None
                and value is not None
                and self._critical is not None
            ):
                self._critical.classify_and_set(
                    str(result_id), str(analyte_code), value, str(units)
                )
                if self._system_state.get("downtime_active"):
                    self._critical.set_notification_mode_required(
                        str(result_id), "phone_or_bleep"
                    )
        hashchain_dict, chain_broken = self._audit.append(event)
        emits_list = ["GENERATE_RESULT"]
        if args.get("analyte_code"):
            emits_list.append("CLASSIFY_RESULT")
        if (
            result_id
            and self._critical is not None
            and self._critical.result_criticality(str(result_id)) != "none"
            and self._system_state.get("downtime_active")
        ):
            emits_list.append("NOTIFY_CRITICAL_RESULT")
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, emits_list, hashchain_dict)

    def _step_release_result(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._qc is not None
        args = event.get("args", {})
        result_id = args.get("result_id")
        if result_id:
            rid = str(result_id)
            if self._critical is not None:
                crit = self._critical.result_criticality(rid)
                if crit in ("CRIT_A", "CRIT_B") and not self._critical.has_ack(rid):
                    hashchain_dict, _ = self._audit.append(event)
                    return self._blocked_result(
                        base, CRIT_NO_ACK, hashchain_dict,
                        violations=[{"invariant_id": "INV-CRIT-002", "status": "VIOLATION"}],
                    )
            can_release, blocked_code = self._qc.can_release_result(rid)
            if not can_release and blocked_code == QC_FAIL_ACTIVE:
                self._qc.hold_result(rid)
                hashchain_dict, _ = self._audit.append(event)
                return self._blocked_result(base, QC_FAIL_ACTIVE, hashchain_dict)
            self._qc.release_result(rid)
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["RELEASE_RESULT"], hashchain_dict)

    def _step_hold_result(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._qc is not None
        args = event.get("args", {})
        result_id = args.get("result_id")
        if result_id:
            self._qc.hold_result(str(result_id))
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["HOLD_RESULT"], hashchain_dict)

    def _step_rerun_request(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["RERUN_REQUEST"], hashchain_dict)

    def _step_release_result_override(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        assert self._qc is not None
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        token_refs = event.get("token_refs", [])
        result_id = args.get("result_id")
        if result_id and token_refs:
            for tid in token_refs:
                v = self._tokens.validity_violation(tid, t_s)
                if v:
                    hashchain_dict, _ = self._audit.append(event)
                    return self._blocked_result(
                        base, QC_FAIL_ACTIVE, hashchain_dict,
                        violations=[{"invariant_id": v, "status": "VIOLATION"}],
                    )
            for tid in token_refs:
                self._tokens.consume_token(tid)
            self._qc.release_result_override_with_drift_flag(str(result_id))
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(
                base, [FORENSIC_FREEZE_LOG], hashchain_dict,
                token_consumed=list(token_refs) if result_id and token_refs else [],
            )
        return self._accepted_result(
            base, ["RELEASE_RESULT"], hashchain_dict,
            token_consumed=list(token_refs) if result_id and token_refs else [],
        )

    def _step_notify_critical_result(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        result_id = args.get("result_id")
        channel = args.get("channel", "")
        receiver_role = args.get("receiver_role", "")
        agent_id = event.get("agent_id", "")
        if result_id and self._critical is not None:
            _, block_reason = self._critical.record_notify(
                str(result_id),
                channel,
                receiver_role,
                str(agent_id),
                t_s,
                message_template_id=args.get("message_template_id"),
                criticality_class=args.get("criticality_class"),
            )
            if block_reason == CRIT_MODE_NOT_ALLOWED:
                hashchain_snap = self._audit.hashchain_snapshot()
                return self._blocked_result(
                    base, CRIT_MODE_NOT_ALLOWED, hashchain_snap,
                )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(base, ["NOTIFY_CRITICAL_RESULT"], hashchain_dict)

    def _step_ack_critical_result(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        result_id = args.get("result_id")
        agent_id = event.get("agent_id", "")
        ack_ok, ack_violation_id, ack_reason_code = True, None, None
        if result_id and self._critical is not None:
            ack_ok, ack_violation_id, ack_reason_code = self._critical.record_ack(
                str(result_id), args, str(agent_id), t_s
            )
            if not ack_ok and ack_reason_code == CRIT_ACK_MISSING_FIELDS:
                hashchain_snap = self._audit.hashchain_snapshot()
                return self._blocked_result(
                    base, CRIT_ACK_MISSING_FIELDS, hashchain_snap,
                )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._finalize_step(
                event,
                {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "violations": [],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                },
            )
        violations_list = list(base.get("violations") or [])
        if not ack_ok and ack_violation_id:
            violations_list.append(
                {
                    "invariant_id": ack_violation_id,
                    "status": "VIOLATION",
                    "reason_code": ack_reason_code or "CRIT_NO_READBACK",
                }
            )
        return self._finalize_step(
            event,
            {
                **base,
                "status": "ACCEPTED",
                "emits": ["ACK_CRITICAL_RESULT"],
                "violations": violations_list,
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            },
        )

    def _step_escalate_critical_result(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        result_id = args.get("result_id")
        next_role = args.get("next_role", "")
        agent_id = event.get("agent_id", "")
        if result_id and next_role and self._critical is not None:
            ok_esc, esc_reason = self._critical.record_escalate(
                str(result_id),
                next_role,
                str(agent_id),
                t_s,
                message_template_id=args.get("message_template_id"),
                criticality_class=args.get("criticality_class"),
            )
            if not ok_esc and esc_reason == CRIT_ESCALATION_OUT_OF_ORDER:
                hashchain_snap = self._audit.hashchain_snapshot()
                return self._blocked_result(
                    base, CRIT_ESCALATION_OUT_OF_ORDER, hashchain_snap,
                )
            if not ok_esc and esc_reason:
                hashchain_snap = self._audit.hashchain_snapshot()
                return self._blocked_result(base, esc_reason, hashchain_snap)
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(
            base, ["ESCALATE_CRITICAL_RESULT"], hashchain_dict,
        )

    def _step_dispatch_transport(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        if self._transport is None:
            return self._step_default(event, base)
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        specimen_ids = args.get("specimen_ids") or []
        origin_site = args.get("origin_site", "")
        dest_site = args.get("dest_site", "")
        agent_id = event.get("agent_id", "")
        cid, reason = self._transport.dispatch(
            [str(s) for s in specimen_ids],
            str(origin_site),
            str(dest_site),
            t_s,
            str(agent_id),
        )
        if reason == TRANSPORT_ROUTE_FORBIDDEN:
            hashchain_snap = self._audit.hashchain_snapshot()
            return self._blocked_result(
                base, TRANSPORT_ROUTE_FORBIDDEN, hashchain_snap,
            )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(
            base, ["DISPATCH_TRANSPORT"], hashchain_dict,
            consignment_id=cid,
        )

    def _step_transport_tick(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        if self._transport is None:
            return self._step_default(event, base)
        t_s = int(event.get("t_s", 0))
        excursions = self._transport.tick(t_s)
        hashchain_dict, chain_broken = self._audit.append(event)
        violations_list = list(base.get("violations") or [])
        for cid, rc in excursions:
            if rc == TRANSPORT_TEMP_EXCURSION:
                violations_list.append(
                    {
                        "invariant_id": "INV-TRANSPORT-001",
                        "status": "VIOLATION",
                        "reason_code": rc,
                    }
                )
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(
                base, [FORENSIC_FREEZE_LOG], hashchain_dict,
                violations=violations_list,
            )
        return self._accepted_result(
            base, ["TRANSPORT_TICK"], hashchain_dict,
            violations=violations_list,
        )

    def _step_receive_transport(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        if self._transport is None:
            return self._step_default(event, base)
        t_s = int(event.get("t_s", 0))
        args = event.get("args", {})
        consignment_id = args.get("consignment_id", "")
        agent_id = event.get("agent_id", "")
        if getattr(self, "_transport_fault_injection", {}).get(
            "force_temp_excursion_on_next_receive"
        ):
            self._transport.inject_temp_excursion(str(consignment_id))
        ok, reason = self._transport.receive(
            str(consignment_id), t_s, str(agent_id)
        )
        if not ok and reason == TRANSPORT_TEMP_EXCURSION:
            hashchain_snap = self._audit.hashchain_snapshot()
            return self._blocked_result(
                base, TRANSPORT_TEMP_EXCURSION, hashchain_snap,
                violations=[
                    {
                        "invariant_id": "INV-TRANSPORT-001",
                        "status": "VIOLATION",
                        "reason_code": reason,
                    }
                ],
            )
        if not ok:
            hashchain_snap = self._audit.hashchain_snapshot()
            rc = reason or TRANSPORT_CHAIN_OF_CUSTODY_BROKEN
            violations_list = list(base.get("violations") or [])
            if rc == TRANSPORT_CHAIN_OF_CUSTODY_BROKEN:
                violations_list.append(
                    {
                        "invariant_id": "INV-COC-001",
                        "status": "VIOLATION",
                        "reason_code": rc,
                    }
                )
            return self._blocked_result(
                base, rc, hashchain_snap,
                violations=violations_list,
            )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(
            base, ["RECEIVE_TRANSPORT"], hashchain_dict,
        )

    def _step_chain_of_custody_sign(
        self, event: StepEventDict | dict[str, Any], base: dict[str, Any]
    ) -> dict[str, Any]:
        if self._transport is None:
            return self._step_default(event, base)
        args = event.get("args", {})
        consignment_id = args.get("consignment_id", "")
        agent_id = event.get("agent_id", "")
        ok, reason = self._transport.chain_of_custody_sign(
            str(consignment_id), str(agent_id)
        )
        if not ok:
            hashchain_snap = self._audit.hashchain_snapshot()
            return self._blocked_result(
                base,
                reason or TRANSPORT_CHAIN_OF_CUSTODY_BROKEN,
                hashchain_snap,
            )
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return self._accepted_result(base, [FORENSIC_FREEZE_LOG], hashchain_dict)
        return self._accepted_result(
            base, ["CHAIN_OF_CUSTODY_SIGN"], hashchain_dict,
        )

    @timed_step_method
    def step(self, event: StepEventDict | dict[str, Any]) -> dict[str, Any]:
        """
        Apply one event. Returns contract: status, emits, violations,
        blocked_reason_code, token_consumed, hashchain.
        Handles MINT_TOKEN, REVOKE_TOKEN, token_refs validation (replay protection).
        """
        assert self._audit is not None, "reset() must be called before step()"
        t_s = int(event.get("t_s", 0))
        self._now_ts = t_s
        # Simulated timing: set clock to t_s and finish any device runs that completed by t_s
        if (
            self._timing_mode == "simulated"
            and self._clock is not None
            and self._device_store is not None
        ):
            self._clock.set(t_s)
            for did, _ in self._device_store.completions(t_s):
                self._device_store.finish_run(did)
            self._device_store.apply_maintenance(t_s)
        action_type = event.get("action_type", "")
        args = event.get("args", {})
        token_refs = event.get("token_refs", [])
        base: dict[str, Any] = {
            "violations": [],
            "token_consumed": [],
            "enforcements": [],
        }

        if self._system_state.get("log_frozen"):
            hashchain = self._audit.hashchain_snapshot()
            return self._blocked_result(base, AUDIT_CHAIN_BROKEN, hashchain)

        # Tool registry gate (B010): any event with tool_id must reference a registered, allowed tool.
        # When allowed_tools is set (e.g. tests), use allowlist; else use RBAC policy (audited authZ).
        tool_id = event.get("tool_id")
        if tool_id is not None and str(tool_id).strip():
            agent_id_tool = str(event.get("agent_id", ""))
            role_id_tool = (
                rbac_get_agent_role(agent_id_tool, self._rbac_policy)
                if agent_id_tool
                else None
            )
            if self._allowed_tools is not None:
                allowed, tool_reason = check_tool_allowed(
                    str(tool_id).strip(),
                    self._tool_registry,
                    agent_id=agent_id_tool,
                    role_id=role_id_tool,
                    allowed_tools=self._allowed_tools,
                )
            else:
                allowed, tool_reason = authz_is_tool_allowed(
                    role_id_tool,
                    str(tool_id).strip(),
                    self._tool_registry,
                    self._rbac_policy,
                    {},
                )
            if not allowed and tool_reason:
                hashchain_tool = self._audit.hashchain_snapshot()
                return self._blocked_result(base, tool_reason, hashchain_tool)
            base["tool_call"] = True
            # Tool selection error (soft fail): allowed by registry & RBAC but inapplicable for current state.
            state_allowed = get_allowed_capabilities_for_state(
                getattr(self, "_state_label", None),
                getattr(self, "_state_tool_capability_map", {}),
            )
            if state_allowed is not None:
                tool_caps = get_tool_capabilities(
                    self._tool_registry, str(tool_id).strip()
                )
                allowed_set = set(state_allowed)
                if tool_caps and any(c not in allowed_set for c in tool_caps):
                    base["tool_selection_error"] = True
                    base.setdefault("violations", []).append(
                        {
                            "invariant_id": "TOOL_SELECTION_ERROR",
                            "status": "VIOLATION",
                            "reason_code": TOOL_SELECTION_ERROR,
                            "message": "Tool allowed by registry and RBAC but inapplicable for current state.",
                        }
                    )
                    base["emits"] = list(base.get("emits", [])) + [TOOL_SELECTION_ERROR]
            # Tool arg validation: typed and range-checked (after allowlist).
            if allowed:
                args_for_tool = args if isinstance(args, dict) else {}
                ok, arg_reason, _details = validate_tool_args(
                    str(tool_id).strip(),
                    args_for_tool,
                    self._tool_registry,
                    self._policy_root,
                )
                if not ok and arg_reason in (TOOL_ARG_SCHEMA_FAIL, TOOL_ARG_RANGE_FAIL):
                    hashchain_arg = self._audit.hashchain_snapshot()
                    return self._blocked_result(
                        base, arg_reason, hashchain_arg,
                        emits=list(base.get("emits", [])),
                    )
                # Tool execution safety wrapper: run adapter, timeout, output validation, sandbox boundary.
                sandbox_ctx: dict[str, Any] = {}
                if getattr(self, "_tool_boundary_policy", None):
                    sandbox_ctx["sandbox"] = ToolSandbox(
                        policy_root=self._policy_root,
                        tool_id=str(tool_id).strip(),
                        role_id=role_id_tool or "",
                        boundary_policy=self._tool_boundary_policy,
                    )
                exec_ok, _tool_result, tool_error = execute_tool_safely(
                    str(tool_id).strip(),
                    args_for_tool,
                    adapter=getattr(self, "_tool_adapter", None),
                    registry=self._tool_registry,
                    policy_root=self._policy_root,
                    timeout_s=getattr(self, "_tool_timeout_s", None),
                    sandbox_ctx=sandbox_ctx,
                )
                if not exec_ok and tool_error is not None:
                    reason_code = tool_error.get("reason_code") or TOOL_EXEC_EXCEPTION
                    msg = tool_error.get("message") or "Tool execution failed"
                    hashchain_exec = self._audit.hashchain_snapshot()
                    violation = {
                        "invariant_id": "TOOL_EXEC_SAFETY",
                        "status": "VIOLATION",
                        "reason_code": reason_code,
                        "message": msg,
                    }
                    return self._blocked_result(
                        base, reason_code, hashchain_exec,
                        emits=[reason_code],
                        violations=[violation],
                    )
        # Runtime control: UPDATE_ROSTER, INJECT_SPECIMEN — always require SYSTEM + signature (trust skeleton).
        if action_type in RUNTIME_CONTROL_ACTION_TYPES:
            agent_id_here = str(event.get("agent_id", ""))
            control_decision: dict[str, Any] = {
                "allowed": False,
                "reason_code": None,
                "role_id": None,
                "signature_passed": False,
            }
            if agent_id_here != "SYSTEM":
                hashchain_snap = self._audit.hashchain_snapshot()
                control_decision["reason_code"] = RBAC_ACTION_DENY
                return self._blocked_result(
                    base, RBAC_ACTION_DENY, hashchain_snap,
                    control_decision=control_decision,
                )
            rbac_allowed_rc, rbac_reason_rc, rbac_decision_rc = rbac_check(
                "SYSTEM", action_type, {}, self._rbac_policy
            )
            control_decision["role_id"] = rbac_decision_rc.get("role_id")
            if not rbac_allowed_rc and rbac_reason_rc:
                hashchain_snap = self._audit.hashchain_snapshot()
                control_decision["reason_code"] = rbac_reason_rc
                return self._blocked_result(
                    base, rbac_reason_rc, hashchain_snap,
                    control_decision=control_decision,
                )
            # Always verify signature for runtime control (no strict_signatures bypass).
            prev_hash_rc = self._audit.last_event_hash
            sig_passed_rc, sig_reason_rc, sig_info_rc = verify_action_signature(
                event,
                prev_hash_rc,
                self._partner_id,
                self._policy_fingerprint,
                self._key_registry,
                t_s,
            )
            control_decision["signature_passed"] = sig_passed_rc is True
            if not event.get("key_id") or not event.get("signature"):
                hashchain_snap = self._audit.hashchain_snapshot()
                control_decision["reason_code"] = SIG_MISSING
                return self._blocked_result(
                    base, SIG_MISSING, hashchain_snap,
                    control_decision=control_decision,
                    signature_verification=sig_info_rc or {},
                )
            if not sig_passed_rc and sig_reason_rc:
                hashchain_snap = self._audit.hashchain_snapshot()
                control_decision["reason_code"] = sig_reason_rc
                return self._blocked_result(
                    base, sig_reason_rc, hashchain_snap,
                    control_decision=control_decision,
                    signature_verification=sig_info_rc or {},
                )
            # Key must be SYSTEM / R_SYSTEM_CONTROL (role mismatch if wrong key).
            key_role = (sig_info_rc or {}).get("key_role_id")
            if key_role != R_SYSTEM_CONTROL_ROLE:
                hashchain_snap = self._audit.hashchain_snapshot()
                control_decision["reason_code"] = SIG_ROLE_MISMATCH
                return self._blocked_result(
                    base, SIG_ROLE_MISMATCH, hashchain_snap,
                    control_decision=control_decision,
                    signature_verification=sig_info_rc or {},
                )
            control_decision["allowed"] = True
            control_decision["reason_code"] = None
            base["control_decision"] = control_decision
            if action_type == "UPDATE_ROSTER":
                roster = args if isinstance(args, dict) else {}
                if isinstance(roster.get("roster"), dict):
                    self._rbac_policy.setdefault("agents", {})
                    self._rbac_policy["agents"] = {
                        **self._rbac_policy.get("agents", {}),
                        **roster["roster"],
                    }
                hashchain_dict, _ = self._audit.append(event)
                return self._finalize_step(
                    event,
                    {
                        **base,
                        "status": "ACCEPTED",
                        "emits": ["UPDATE_ROSTER"],
                        "blocked_reason_code": None,
                        "hashchain": hashchain_dict,
                    },
                )
            if action_type == "INJECT_SPECIMEN":
                spec = dict(args) if isinstance(args, dict) else {}
                spec.setdefault("status", "arrived_at_reception")
                spec.setdefault("last_reason_code", None)
                if self._specimens is not None and self._specimens.add_specimen(spec):
                    hashchain_dict, _ = self._audit.append(event)
                    return self._finalize_step(
                        event,
                        {
                            **base,
                            "status": "ACCEPTED",
                            "emits": ["INJECT_SPECIMEN"],
                            "blocked_reason_code": None,
                            "hashchain": hashchain_dict,
                        },
                    )
                hashchain_snap = self._audit.hashchain_snapshot()
                return self._blocked_result(
                    base, RC_INJECT_SPECIMEN_DUPLICATE, hashchain_snap,
                )

        # Device colocation gate for START_RUN / START_RUN_OVERRIDE (before RBAC so domain reason is returned, e.g. GS-019)
        if action_type in ("START_RUN", "START_RUN_OVERRIDE"):
            device_id = args.get("device_id")
            _agent_id = str(event.get("agent_id", ""))
            if device_id and self._zones is not None:
                device_zone = self._device_zone.get(str(device_id))
                agent_zone = (
                    self._zones.get_agent_zone(_agent_id) if _agent_id else None
                )
                if device_zone and agent_zone is not None and agent_zone != device_zone:
                    hashchain_snap = self._audit.hashchain_snapshot()
                    return self._blocked_result(
                        base, RC_DEVICE_NOT_COLOCATED, hashchain_snap,
                        violations=[{"invariant_id": "INV-ZONE-002", "status": "VIOLATION"}],
                    )

        # RBAC gate (first gate: before tokens, before domain logic)
        agent_id = str(event.get("agent_id", ""))
        rbac_context: dict[str, Any] = {}
        if self._zones is not None and agent_id:
            rbac_context["zone_id"] = self._zones.get_agent_zone(agent_id)
        rbac_context["device_id"] = args.get("device_id")
        rbac_allowed, rbac_reason, rbac_decision = rbac_check(
            agent_id, action_type, rbac_context, self._rbac_policy
        )
        base["rbac_decision"] = rbac_decision
        if not rbac_allowed and rbac_reason:
            hashchain_snap = self._audit.hashchain_snapshot()
            return self._blocked_result(base, rbac_reason, hashchain_snap)

        # Capability gate (B006): after RBAC, before domain mutation
        if self._capability_policy and self._capability_policy.get("profiles"):
            role_id = rbac_decision.get("role_id")
            profile = get_profile_for_agent(
                agent_id,
                role_id,
                self._capability_policy,
                self._rbac_policy.get("agents") if self._rbac_policy else None,
            )
            rbac_allowed_actions = rbac_get_allowed_actions(agent_id, self._rbac_policy)
            action_count = self._episode_agent_action_count.get(agent_id, 0)
            override_count = self._episode_agent_override_count.get(agent_id, 0)
            cap_allowed, cap_reason = check_capability(
                action_type,
                event,
                profile,
                self._capability_policy,
                rbac_allowed_actions,
                action_count,
                override_count,
            )
            if not cap_allowed and cap_reason:
                hashchain_snap = self._audit.hashchain_snapshot()
                return self._blocked_result(
                    base, cap_reason, hashchain_snap,
                    emits=["AGENT_SCOPE_VIOLATION"],
                    capability_decision={
                        "allowed": False,
                        "reason_code": cap_reason,
                        "action_count": action_count,
                        "override_count": override_count,
                    },
                )

        prev_hash = self._audit.last_event_hash
        sig_passed: bool | None = None
        sig_reason: str | None = None
        sig_info: dict[str, Any] | None = None
        if event.get("key_id") or event.get("signature"):
            passed, reason, info = verify_action_signature(
                event,
                prev_hash,
                self._partner_id,
                self._policy_fingerprint,
                self._key_registry,
                t_s,
            )
            sig_passed = passed
            sig_reason = reason
            sig_info = info or {}
        self._step_signature_verification: dict[str, Any] | None = sig_info
        if self._strict_signatures and is_mutating_action(action_type):
            if not event.get("key_id") or not event.get("signature"):
                hashchain_snap = self._audit.hashchain_snapshot()
                return self._blocked_result(
                    base, SIG_MISSING, hashchain_snap,
                    signature_verification={
                        "passed": False,
                        "reason_code": "SIG_MISSING",
                        "key_id": event.get("key_id"),
                    },
                )
            if sig_passed is False and sig_reason:
                hashchain_snap = self._audit.hashchain_snapshot()
                return self._blocked_result(
                    base, sig_reason, hashchain_snap,
                    signature_verification=sig_info,
                )
            # INV-SIG-002: key role must match RBAC role for agent_id
            if sig_passed is True and sig_info:
                agent_role = rbac_get_agent_role(agent_id, self._rbac_policy)
                key_role = sig_info.get("key_role_id")
                if (
                    agent_role is not None
                    and key_role is not None
                    and agent_role != key_role
                ):
                    hashchain_snap = self._audit.hashchain_snapshot()
                    return self._blocked_result(
                        base, SIG_ROLE_MISMATCH, hashchain_snap,
                        signature_verification=sig_info,
                    )

        assert self._zones is not None, "zones not initialized"

        handler_name = _STEP_DISPATCH.get(action_type)
        if handler_name is not None:
            return getattr(self, handler_name)(event, base)

        # Actions that reference token_refs: validate then consume if required
        if token_refs:
            token_violations: list[dict[str, Any]] = []
            for tid in token_refs:
                v = self._tokens.validity_violation(tid, t_s)
                if v:
                    token_violations.append({"invariant_id": v, "status": "VIOLATION"})
            if token_violations:
                hashchain_dict, _ = self._audit.append(event)
                blocked_code = RBAC_RESTRICTED_ENTRY_DENY
                if any(
                    v.get("invariant_id") == "INV-TOK-006" for v in token_violations
                ):
                    blocked_code = AUDIT_CHAIN_BROKEN
                elif any(
                    v.get("invariant_id") == "INV-TOK-002" for v in token_violations
                ):
                    blocked_code = "INV-TOK-002"
                return self._blocked_result(
                    base, blocked_code, hashchain_dict,
                    violations=token_violations,
                )
            # OPEN_DOOR D_RESTRICTED_AIRLOCK requires TOKEN_RESTRICTED_ENTRY; consume
            if (
                action_type == "OPEN_DOOR"
                and args.get("door_id") == "D_RESTRICTED_AIRLOCK"
            ):
                for tid in token_refs:
                    self._tokens.consume_token(tid)
                self._zones.open_door("D_RESTRICTED_AIRLOCK", t_s)
                hashchain_dict, chain_broken = self._audit.append(event)
                if chain_broken:
                    self._system_state["log_frozen"] = True
                    self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                    return self._accepted_result(
                        base, [FORENSIC_FREEZE_LOG], hashchain_dict,
                        token_consumed=list(token_refs),
                    )
                return self._accepted_result(
                    base, [action_type], hashchain_dict,
                    token_consumed=list(token_refs),
                )

        handler_name = _STEP_DISPATCH_LATE.get(action_type)
        if handler_name is not None:
            return getattr(self, handler_name)(event, base)
        return self._step_default(event, base)


    def query(self, expr: str) -> Any:
        """
        Query state for runner state_assertions.
        Supports: system_state('log_frozen'), last_reason_code_system, token_active.
        Uses a dispatch table (exact match then compiled patterns) for consistent lookup.
        """
        expr = expr.strip()
        if expr == "last_reason_code_system":
            return self._system_state.get("last_reason_code_system")
        if expr.startswith("system_state(") and "log_frozen" in expr:
            return "true" if self._system_state.get("log_frozen", False) else "false"
        if "token_active" in expr or expr == "token_active":
            return self._tokens.list_active_ids()
        m = _RE_QUERY_ZONE_STATE.match(expr)
        if m and self._zones is not None:
            return self._zones.zone_state(m.group(1))
        m = _RE_QUERY_SPECIMEN_STATUS.match(expr)
        if m and self._specimens is not None:
            return self._specimens.specimen_status(m.group(1))
        m = _RE_QUERY_LAST_REASON_CODE.match(expr)
        if m and self._specimens is not None:
            return self._specimens.last_reason_code(m.group(1))
        m = _RE_QUERY_RESULT_STATUS.match(expr)
        if m and self._qc is not None:
            return self._qc.result_status(m.group(1))
        m = _RE_QUERY_RESULT_FLAGS.match(expr)
        if m and self._qc is not None:
            return self._qc.result_flags(m.group(1))
        m = _RE_QUERY_RESULT_CRIT.match(expr)
        if m and self._critical is not None:
            return self._critical.result_criticality(m.group(1))
        m = _RE_QUERY_COMM_EXISTS.match(expr)
        if m and self._critical is not None:
            return (
                "true"
                if self._critical.comm_record_exists(m.group(1))
                else "false"
            )
        m = _RE_QUERY_NOTIF_MODE.match(expr)
        if m and self._critical is not None:
            return self._critical.notification_mode_required(m.group(1))
        m = _RE_QUERY_QUEUE_HEAD.match(expr)
        if m and self._queues is not None:
            return self._queues.queue_head(m.group(1))
        m = _RE_QUERY_QUEUE_LENGTH.match(expr)
        if m and self._queues is not None:
            return self._queues.queue_length(m.group(1))
        m = _RE_QUERY_AGENT_ZONE.match(expr)
        if m and self._zones is not None:
            return self._zones.get_agent_zone(m.group(1))
        m = _RE_QUERY_DOOR_STATE.match(expr)
        if m and self._zones is not None:
            door_id = m.group(1)
            is_open, open_since_ts = self._zones.get_door_state(door_id)
            duration_s = (
                (self._now_ts - open_since_ts) if (open_since_ts is not None) else 0
            )
            return {
                "open": is_open,
                "open_since_ts": open_since_ts,
                "open_duration_s": duration_s,
            }
        if expr == "specimen_counts" and self._specimens is not None:
            return self._specimens.get_status_counts()
        m = _RE_QUERY_DEVICE_QC.match(expr)
        if m and self._qc is not None:
            return self._qc.device_qc_state(m.group(1))
        m = _RE_QUERY_DEVICE_STATE.match(expr)
        if m and self._device_store is not None:
            return self._device_store.device_state(m.group(1))
        if expr == "transport_consignments" and self._transport is not None:
            return self._transport.list_consignments_info()
        if expr == "last_event_hash" and self._audit is not None:
            return self._audit.last_event_hash
        if expr == "accepted_specimen_ids_not_in_queue":
            if self._specimens is None or self._queues is None:
                return []
            accepted = self._specimens.list_specimen_ids_by_status("accepted")
            enqueued = set(self._queues.all_enqueued_work_ids())
            return [s for s in accepted if s not in enqueued]
        if expr == "releasable_result_ids":
            if self._qc is None:
                return []
            candidates = self._qc.list_result_ids_with_status("generated", "held")
            out: list[str] = []
            for rid in candidates:
                can_release, _ = self._qc.can_release_result(rid)
                if not can_release:
                    continue
                if self._critical is not None:
                    crit = self._critical.result_criticality(rid)
                    if crit in ("CRIT_A", "CRIT_B") and not self._critical.has_ack(rid):
                        continue
                out.append(rid)
            return out
        raise ValueError(f"Unsupported query: {expr!r}")

    def query_many(self, exprs: list[str]) -> dict[str, Any]:
        """
        Evaluate multiple query expressions in one call. Returns a dict mapping each
        expression to its result. Expressions that raise ValueError are omitted from
        the result (caller can use defaults).
        """
        out: dict[str, Any] = {}
        for expr in exprs:
            try:
                out[expr] = self.query(expr)
            except ValueError:
                pass
        return out

    def get_agent_role(self, agent_id: str) -> str | None:
        """
        Return current role_id for agent_id from RBAC policy (updated by UPDATE_ROSTER).
        Used for role-aware prompt routing and shift-change.
        """
        agents = self._rbac_policy.get("agents") if self._rbac_policy else None
        if not isinstance(agents, dict):
            return None
        return agents.get(agent_id)

    def get_timing_summary(self) -> dict[str, Any]:
        """
        Return timing_mode, episode_time_s (simulated clock or None), device_busy_s (per-device busy seconds).
        Used by benchmark runner for utilization and p95 turnaround labeling.
        """
        episode_time_s: int | None = None
        if self._clock is not None:
            episode_time_s = self._clock.now_ts
        device_busy_s: dict[str, int] = {}
        if self._device_store is not None:
            device_busy_s = self._device_store.get_all_total_busy_s()
        return {
            "timing_mode": self._timing_mode,
            "episode_time_s": episode_time_s,
            "device_busy_s": device_busy_s,
        }
