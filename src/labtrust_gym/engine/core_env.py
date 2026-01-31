"""
Minimal engine: reset, step (contract output), query.

Supports GS-022: audit hashchain, fault injection, forensic freeze.
Supports GS-010--013: token lifecycle, dual approval, replay protection.
Supports GS-008, GS-009, GS-020: zones, doors, MOVE adjacency, OPEN_DOOR restricted, door-open-too-long.
Supports GS-003, GS-004, GS-005, GS-021: reception acceptance (specimens, HOLD_SPECIMEN reason_code).
Supports GS-014, GS-015: QC model, result gating, RELEASE_RESULT_OVERRIDE with drift token.
Once log_frozen, all steps BLOCKED with blocked_reason_code AUDIT_CHAIN_BROKEN.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from labtrust_gym.engine.audit_log import AuditLog
from labtrust_gym.engine.catalogue_runtime import (
    check_stability,
    check_temp_out_of_band,
    load_stability_policy,
)
from labtrust_gym.engine.critical import CriticalStore, load_critical_thresholds
from labtrust_gym.engine.qc import QCStore
from labtrust_gym.engine.queueing import QueueStore
from labtrust_gym.engine.specimens import SpecimenStore
from labtrust_gym.engine.tokens_runtime import TokenStore
from labtrust_gym.engine.clock import Clock
from labtrust_gym.engine.devices import DeviceStore, load_equipment_registry
from labtrust_gym.engine.rng import RNG
from labtrust_gym.engine.invariants_runtime import (
    InvariantsRuntime,
    merge_violations_by_invariant_id,
)
from labtrust_gym.engine.enforcement import (
    EnforcementEngine,
    apply_enforcement,
)
from labtrust_gym.engine.zones import (
    ZoneState,
    build_device_zone_map,
    get_default_device_zone_map,
    load_zone_layout,
)
from labtrust_gym.policy.tokens import (
    Token,
    load_token_registry,
    validate_dual_approval,
)
from labtrust_gym.runner.adapter import LabTrustEnvAdapter


AUDIT_CHAIN_BROKEN = "AUDIT_CHAIN_BROKEN"
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

# Minimal token type config when policy file not found (GS-010 dual approval).
_DEFAULT_TOKEN_TYPES = {
    "OVERRIDE_RISK_ACCEPTANCE": {"approvals_required": 2, "ttl_s": 3600},
    "TOKEN_RESTRICTED_ENTRY": {"approvals_required": 1, "ttl_s": 900},
}


class CoreEnv(LabTrustEnvAdapter):
    """
    Minimal engine: audit log, token store, forensic freeze, contract step output.
    Implements LabTrustEnvAdapter for the golden runner.
    """

    def __init__(self) -> None:
        self._audit: AuditLog | None = None
        self._system_state: Dict[str, Any] = {}
        self._tokens: TokenStore = TokenStore()
        self._token_registry: Dict[str, Any] = {}
        self._zones: ZoneState | None = None
        self._device_zone: Dict[str, str] = {}
        self._specimens: SpecimenStore | None = None
        self._qc: QCStore | None = None
        self._critical: CriticalStore | None = None
        self._queues: QueueStore | None = None
        self._now_ts: int = 0
        self._invariants_runtime: InvariantsRuntime | None = None
        self._enforcement_engine: EnforcementEngine | None = None
        self._enforcement_enabled: bool = False

    def reset(
        self,
        initial_state: Dict[str, Any],
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
        from labtrust_gym.engine.critical import default_thresholds
        th = default_thresholds()
        crit_path = Path("policy/critical/critical_thresholds.v0.1.yaml")
        if crit_path.exists():
            try:
                th = load_critical_thresholds(crit_path)
            except Exception:
                pass
        self._critical.load_thresholds(th)
        self._queues = QueueStore()
        self._queues.set_known_devices(list(self._device_zone.keys()))
        self._timing_mode = str(initial_state.get("timing_mode", "explicit")).strip().lower()
        if self._timing_mode not in ("explicit", "simulated"):
            self._timing_mode = "explicit"
        self._clock = None
        self._device_store = None
        self._rng = None
        if self._timing_mode == "simulated":
            self._rng = RNG(rng_seed)
            registry = load_equipment_registry()
            self._device_store = DeviceStore(registry=registry, rng=self._rng)
            self._device_store.set_known_devices(list(self._device_zone.keys()))
            self._clock = Clock()
        self._stability_policy: Dict[str, Any] = {}
        stab_path = Path("policy/stability/stability_policy.v0.1.yaml")
        if stab_path.exists():
            try:
                self._stability_policy = load_stability_policy(stab_path)
            except Exception:
                pass
        inv_path = Path("policy/invariants/invariant_registry.v1.0.yaml")
        if inv_path.exists():
            try:
                self._invariants_runtime = InvariantsRuntime(inv_path)
            except Exception:
                self._invariants_runtime = None
        else:
            self._invariants_runtime = None
        self._enforcement_enabled = bool(initial_state.get("enforcement_enabled", False))
        if self._enforcement_enabled:
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

    def _finalize_step(
        self, event: Dict[str, Any], result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge registry invariant violations; optionally apply enforcement and record to audit."""
        if result.get("status") != "ACCEPTED":
            return result
        if self._invariants_runtime is not None:
            legacy = result.get("violations") or []
            registry = self._invariants_runtime.evaluate(self, event, result)
            result = {**result, "violations": merge_violations_by_invariant_id(legacy, registry)}
        enforcements: List[Dict[str, Any]] = result.get("enforcements") or []
        if self._enforcement_enabled and self._enforcement_engine and self._audit is not None:
            violations = result.get("violations") or []
            enforcements = apply_enforcement(
                event,
                violations,
                self._enforcement_engine,
                audit_callback=None,
            )
            for i, enf in enumerate(enforcements):
                self._audit.append({
                    "event_id": f"{event.get('event_id', 'step')}_enf_{i}",
                    "event_type": "ENFORCEMENT",
                    "rule_id": enf.get("rule_id"),
                    "action_type": enf.get("type"),
                    "target": enf.get("target"),
                    "duration_s": enf.get("duration_s"),
                    "reason_code": enf.get("reason_code"),
                    "zone_id": enf.get("zone_id"),
                })
        result = {**result, "enforcements": enforcements}
        return result

    def step(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply one event. Returns contract: status, emits, violations,
        blocked_reason_code, token_consumed, hashchain.
        Handles MINT_TOKEN, REVOKE_TOKEN, token_refs validation (replay protection).
        """
        assert self._audit is not None, "reset() must be called before step()"
        t_s = int(event.get("t_s", 0))
        self._now_ts = t_s
        # Simulated timing: set clock to t_s and finish any device runs that completed by t_s
        if self._timing_mode == "simulated" and self._clock is not None and self._device_store is not None:
            self._clock.set(t_s)
            for did, _ in self._device_store.completions(t_s):
                self._device_store.finish_run(did)
        action_type = event.get("action_type", "")
        args = event.get("args", {})
        token_refs = event.get("token_refs", [])
        base = {
            "violations": [],
            "token_consumed": [],
            "enforcements": [],
        }

        if self._system_state.get("log_frozen"):
            hashchain = self._audit.hashchain_snapshot()
            return {
                **base,
                "status": "BLOCKED",
                "emits": [],
                "blocked_reason_code": AUDIT_CHAIN_BROKEN,
                "hashchain": hashchain,
            }

        assert self._zones is not None, "zones not initialized"

        # TICK: check door-open-too-long
        if action_type == "TICK":
            violations, emits = self._zones.tick(t_s)
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return self._finalize_step(event, {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "violations": violations,
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                })
            return self._finalize_step(event, {
                **base,
                "status": "ACCEPTED",
                "emits": emits if emits else [],
                "violations": violations,
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            })

        # MOVE: adjacency check; restricted zone requires token
        if action_type == "MOVE":
            from_zone = str(args.get("from_zone", ""))
            to_zone = str(args.get("to_zone", ""))
            entity_type = args.get("entity_type", "Agent")
            agent_id = str(event.get("agent_id", ""))
            if entity_type == "Specimen":
                ok = self._zones.is_adjacent(from_zone, to_zone)
                move_violations = [] if ok else [{"invariant_id": "INV-ZONE-001", "status": "VIOLATION"}]
                blocked_code = None if ok else "RC_ILLEGAL_MOVE"
            else:
                if not agent_id:
                    agent_id = str(args.get("entity_id", event.get("agent_id", "")))
                ok, move_violations, blocked_code = self._zones.move(agent_id, from_zone, to_zone)
            if not ok:
                hashchain_dict, _ = self._audit.append(event)
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": blocked_code,
                    "violations": move_violations,
                    "hashchain": hashchain_dict,
                }
            if to_zone == Z_RESTRICTED_BIOHAZARD:
                if not token_refs:
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": RBAC_RESTRICTED_ENTRY_DENY,
                        "violations": [
                            {"invariant_id": "INV-ZONE-004", "status": "VIOLATION"},
                            {"invariant_id": "INV-TOK-003", "status": "VIOLATION"},
                        ],
                        "hashchain": hashchain_dict,
                    }
                for tid in token_refs:
                    v = self._tokens.validity_violation(tid, t_s)
                    if v:
                        hashchain_dict, _ = self._audit.append(event)
                        return {
                            **base,
                            "status": "BLOCKED",
                            "emits": [],
                            "blocked_reason_code": RBAC_RESTRICTED_ENTRY_DENY,
                            "violations": [{"invariant_id": v, "status": "VIOLATION"}],
                            "hashchain": hashchain_dict,
                        }
                for tid in token_refs:
                    self._tokens.consume_token(tid)
                hashchain_dict, chain_broken = self._audit.append(event)
                if chain_broken:
                    self._system_state["log_frozen"] = True
                    self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                    return {
                        **base,
                        "status": "ACCEPTED",
                        "emits": [FORENSIC_FREEZE_LOG],
                        "blocked_reason_code": None,
                        "token_consumed": list(token_refs),
                        "hashchain": hashchain_dict,
                    }
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": ["MOVE"],
                    "blocked_reason_code": None,
                    "token_consumed": list(token_refs),
                    "hashchain": hashchain_dict,
                }
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["MOVE"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }

        # MINT_TOKEN
        if action_type == "MINT_TOKEN":
            approvals = args.get("approvals", [])
            if isinstance(approvals, list) and approvals:
                pass
            else:
                approvals = []
            token_type = args.get("token_type", "")
            ok, violation = validate_dual_approval(
                approvals, token_type, self._token_registry
            )
            if not ok and violation:
                hashchain_dict, _ = self._audit.append(event)
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": violation,
                    "violations": [{"invariant_id": violation, "status": "VIOLATION"}],
                    "hashchain": hashchain_dict,
                }
            subject_type = args.get("subject_type", "")
            subject_id = args.get("subject_id", "")
            reason_code = args.get("reason_code")
            token_types = self._token_registry.get("token_types") or _DEFAULT_TOKEN_TYPES
            meta = token_types.get(token_type, {})
            ttl_s = int(meta.get("ttl_s", 3600))
            token_id = f"T_OVR_{subject_id}" if "OVERRIDE" in token_type else f"T_{token_type}_{subject_id}"
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
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": "INV-TOK-001",
                    "violations": [{"invariant_id": "INV-TOK-001", "status": "VIOLATION"}],
                    "hashchain": hashchain_dict,
                }
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["MINT_TOKEN"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }

        # REVOKE_TOKEN
        if action_type == "REVOKE_TOKEN":
            token_id = args.get("token_id")
            if token_id:
                self._tokens.revoke_token(token_id)
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["REVOKE_TOKEN"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }

        # Actions that reference token_refs: validate then consume if required
        if token_refs:
            violations: List[Dict[str, Any]] = []
            for tid in token_refs:
                v = self._tokens.validity_violation(tid, t_s)
                if v:
                    violations.append({"invariant_id": v, "status": "VIOLATION"})
            if violations:
                hashchain_dict, _ = self._audit.append(event)
                blocked_code = RBAC_RESTRICTED_ENTRY_DENY
                if any(v.get("invariant_id") == "INV-TOK-006" for v in violations):
                    blocked_code = AUDIT_CHAIN_BROKEN
                elif any(v.get("invariant_id") == "INV-TOK-002" for v in violations):
                    blocked_code = "INV-TOK-002"
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": blocked_code,
                    "violations": violations,
                    "hashchain": hashchain_dict,
                }
            # OPEN_DOOR D_RESTRICTED_AIRLOCK requires TOKEN_RESTRICTED_ENTRY; consume
            if action_type == "OPEN_DOOR" and args.get("door_id") == "D_RESTRICTED_AIRLOCK":
                for tid in token_refs:
                    self._tokens.consume_token(tid)
                self._zones.open_door("D_RESTRICTED_AIRLOCK", t_s)
                hashchain_dict, chain_broken = self._audit.append(event)
                if chain_broken:
                    self._system_state["log_frozen"] = True
                    self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                    return {
                        **base,
                        "status": "ACCEPTED",
                        "emits": [FORENSIC_FREEZE_LOG],
                        "blocked_reason_code": None,
                        "token_consumed": list(token_refs),
                        "hashchain": hashchain_dict,
                    }
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [action_type],
                    "blocked_reason_code": None,
                    "token_consumed": list(token_refs),
                    "hashchain": hashchain_dict,
                }

        # OPEN_DOOR D_RESTRICTED_AIRLOCK without valid token
        if action_type == "OPEN_DOOR" and args.get("door_id") == "D_RESTRICTED_AIRLOCK":
            hashchain_dict, _ = self._audit.append(event)
            return {
                **base,
                "status": "BLOCKED",
                "emits": [],
                "blocked_reason_code": RBAC_RESTRICTED_ENTRY_DENY,
                "violations": [
                    {"invariant_id": "INV-ZONE-004", "status": "VIOLATION"},
                    {"invariant_id": "INV-TOK-003", "status": "VIOLATION"},
                ],
                "hashchain": hashchain_dict,
            }

        # CENTRIFUGE_START (GS-001): co-location check; INV-ZONE-002 from invariants_runtime
        if action_type == "CENTRIFUGE_START":
            device_id = args.get("device_id")
            agent_id = str(event.get("agent_id", ""))
            violations_list: List[Dict[str, Any]] = []
            if device_id and self._zones is not None:
                device_zone = self._device_zone.get(str(device_id))
                agent_zone = self._zones.get_agent_zone(agent_id) if agent_id else None
                if device_zone and agent_zone is not None and agent_zone != device_zone:
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": RC_DEVICE_NOT_COLOCATED,
                        "violations": [
                            {"invariant_id": "INV-ZONE-002", "status": "VIOLATION"},
                        ],
                        "hashchain": hashchain_dict,
                    }
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

        # QUEUE_RUN (GS-002): per-device queue, STAT/URGENT/ROUTINE ordering
        if action_type == "QUEUE_RUN":
            assert self._queues is not None and self._zones is not None
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
            priority_raw = args.get("priority") or args.get("priority_class") or "ROUTINE"
            priority_class = (
                str(priority_raw).upper()
                if str(priority_raw).upper() in ("STAT", "URGENT", "ROUTINE")
                else "ROUTINE"
            )
            if not device_id or not work_id:
                hashchain_dict, _ = self._audit.append(event)
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": RC_QUEUE_BAD_PAYLOAD,
                    "hashchain": hashchain_dict,
                }
            if not self._queues.is_known_device(str(device_id)):
                hashchain_dict, _ = self._audit.append(event)
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": RC_DEVICE_UNKNOWN,
                    "hashchain": hashchain_dict,
                }
            agent_id = str(event.get("agent_id", ""))
            if device_id and self._device_zone.get(str(device_id)) and agent_id:
                device_zone = self._device_zone.get(str(device_id))
                agent_zone = self._zones.get_agent_zone(agent_id)
                if agent_zone is not None and device_zone != agent_zone:
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": RC_DEVICE_NOT_COLOCATED,
                        "violations": [
                            {"invariant_id": "INV-ZONE-002", "status": "VIOLATION"},
                        ],
                        "hashchain": hashchain_dict,
                    }
            ok = self._queues.enqueue(
                str(device_id),
                str(work_id),
                priority_class,
                t_s,
                agent_id,
                event.get("reason_code") or args.get("reason_code"),
                allow_duplicate_work_id=True,
            )
            if not ok:
                hashchain_dict, _ = self._audit.append(event)
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": RC_QUEUE_DUPLICATE_WORK_ID,
                    "hashchain": hashchain_dict,
                }
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["QUEUE_RUN"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }

        # Reception: specimens (GS-003, GS-004, GS-005, GS-021)
        assert self._specimens is not None, "specimens not initialized"
        if action_type == "CREATE_ACCESSION":
            specimen_id = args.get("specimen_id")
            if specimen_id and self._specimens.create_accession(str(specimen_id)):
                hashchain_dict, chain_broken = self._audit.append(event)
                if chain_broken:
                    self._system_state["log_frozen"] = True
                    self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                    return {
                        **base,
                        "status": "ACCEPTED",
                        "emits": [FORENSIC_FREEZE_LOG],
                        "blocked_reason_code": None,
                        "hashchain": hashchain_dict,
                    }
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": ["CREATE_ACCESSION"],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
        if action_type == "CHECK_ACCEPTANCE_RULES":
            specimen_id = args.get("specimen_id")
            id_match = args.get("id_match")
            if specimen_id:
                self._specimens.check_acceptance_rules(str(specimen_id), id_match)
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["CHECK_ACCEPTANCE_RULES"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        if action_type == "ACCEPT_SPECIMEN":
            specimen_id = args.get("specimen_id")
            if specimen_id:
                outcome, emits, blocked_code, _ = self._specimens.accept_specimen(str(specimen_id))
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
            # no specimen_id: fall through to default
        if action_type == "HOLD_SPECIMEN":
            reason_code = event.get("reason_code") or args.get("reason_code")
            specimen_id = args.get("specimen_id")
            if not specimen_id:
                hashchain_dict, _ = self._audit.append(event)
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": ["HOLD_SPECIMEN"],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            ok, blocked_code = self._specimens.hold_specimen(str(specimen_id), reason_code)
            if not ok and blocked_code == AUDIT_MISSING_REASON_CODE:
                hashchain_dict, _ = self._audit.append(event)
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": AUDIT_MISSING_REASON_CODE,
                    "hashchain": hashchain_dict,
                }
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["HOLD_SPECIMEN"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        if action_type == "REJECT_SPECIMEN":
            specimen_id = args.get("specimen_id")
            reason_code = event.get("reason_code") or args.get("reason_code")
            if specimen_id and self._specimens.reject_specimen(str(specimen_id), reason_code):
                hashchain_dict, chain_broken = self._audit.append(event)
                if chain_broken:
                    self._system_state["log_frozen"] = True
                    self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                    return {
                        **base,
                        "status": "ACCEPTED",
                        "emits": [FORENSIC_FREEZE_LOG],
                        "blocked_reason_code": None,
                        "hashchain": hashchain_dict,
                    }
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": ["REJECT_SPECIMEN"],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }

        # CENTRIFUGE_END: update specimen separated_ts_s
        if action_type == "CENTRIFUGE_END":
            specimen_ids = args.get("specimen_ids") or []
            separated_ts_s = args.get("separated_ts_s", t_s)
            for sid in specimen_ids:
                self._specimens.set_separated_ts(str(sid), int(separated_ts_s))
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["CENTRIFUGE_END"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        # ALIQUOT_CREATE: record aliquot_id -> specimen_id
        if action_type == "ALIQUOT_CREATE":
            specimen_id = args.get("specimen_id")
            aliquot_id = args.get("aliquot_id")
            if specimen_id and aliquot_id:
                self._specimens.record_aliquot(str(aliquot_id), str(specimen_id))
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["ALIQUOT_CREATE"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        # QC and results (GS-014, GS-015)
        assert self._qc is not None, "qc not initialized"
        if action_type == "START_RUN":
            # Co-location: agent must be in device zone (GS-019)
            device_id = args.get("device_id")
            agent_id = str(event.get("agent_id", ""))
            if device_id and self._zones is not None:
                device_zone = self._device_zone.get(str(device_id))
                agent_zone = self._zones.get_agent_zone(agent_id) if agent_id else None
                if device_zone and agent_zone is not None and agent_zone != device_zone:
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": RC_DEVICE_NOT_COLOCATED,
                        "violations": [
                            {"invariant_id": "INV-ZONE-002", "status": "VIOLATION"},
                        ],
                        "hashchain": hashchain_dict,
                    }
            # Simulated timing: device must be IDLE to start a run
            if (
                self._timing_mode == "simulated"
                and self._device_store is not None
                and device_id
                and not self._device_store.can_start_run(str(device_id))
            ):
                hashchain_dict, _ = self._audit.append(event)
                return {
                    **base,
                    "status": "BLOCKED",
                    "emits": [],
                    "blocked_reason_code": RC_DEVICE_BUSY,
                    "violations": [],
                    "hashchain": hashchain_dict,
                }
            # Queue: consume head if no explicit work/specimen/aliquot; else enforce head == work_id
            specimen_ids: Optional[List[str]] = None
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
                        return {
                            **base,
                            "status": "BLOCKED",
                            "emits": [],
                            "blocked_reason_code": RC_QUEUE_EMPTY,
                            "hashchain": hashchain_dict,
                        }
                    specimen_ids = [work_id_from_queue]
                elif resolved_from_args or explicit_work_id:
                    work_id = explicit_work_id or (
                        resolved_from_args[0] if resolved_from_args else None
                    )
                    if work_id is not None:
                        head = self._queues.queue_head(str(device_id))
                        if head is not None and head != str(work_id):
                            hashchain_dict, _ = self._audit.append(event)
                            return {
                                **base,
                                "status": "BLOCKED",
                                "emits": [],
                                "blocked_reason_code": RC_QUEUE_HEAD_MISMATCH,
                                "hashchain": hashchain_dict,
                            }
                        if head == str(work_id):
                            self._queues.consume_head(str(device_id))
                    specimen_ids = resolved_from_args or (
                        [str(explicit_work_id)] if explicit_work_id else []
                    )
            if specimen_ids is None:
                specimen_ids = self._specimens.resolve_to_specimen_ids(
                    args.get("specimen_ids"),
                    args.get("aliquot_ids"),
                )
            violations: List[Dict[str, Any]] = []
            for sid in specimen_ids or []:
                spec = self._specimens.get(sid)
                if not spec:
                    continue
                panel_id = spec.get("panel_id") or "BIOCHEM_PANEL_CORE"
                collection_ts_s = int(spec.get("collection_ts_s", 0))
                separated_ts_s = spec.get("separated_ts_s")
                if separated_ts_s is not None:
                    separated_ts_s = int(separated_ts_s)
                temp_band = spec.get("temp_band") or "AMBIENT_20_25"
                ok, viol_id, reason, pass_inv = check_stability(
                    collection_ts_s,
                    separated_ts_s,
                    t_s,
                    panel_id,
                    self._stability_policy,
                    temp_band,
                )
                if not ok and not token_refs:
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": reason or TIME_EXPIRED,
                        "violations": [{"invariant_id": viol_id, "status": "VIOLATION"}],
                        "hashchain": hashchain_dict,
                    }
                if check_temp_out_of_band(
                    spec.get("storage_requirement"),
                    spec.get("temp_exposure_log"),
                ) and not token_refs:
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": TEMP_OUT_OF_BAND,
                        "violations": [
                            {"invariant_id": "INV-ZONE-006", "status": "VIOLATION"},
                        ],
                        "hashchain": hashchain_dict,
                    }
                # INV-STAB-BIOCHEM-001:PASS from invariants_runtime when stability ok
            device_id = args.get("device_id")
            run_id = args.get("run_id")
            if device_id and run_id:
                self._qc.register_run(str(run_id), str(device_id))
            # Simulated timing: schedule run completion (service time from RNG)
            first_panel_id: Optional[str] = None
            if specimen_ids and self._specimens:
                first_spec = self._specimens.get(specimen_ids[0]) if specimen_ids else None
                first_panel_id = first_spec.get("panel_id") if first_spec else None
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
                    work_id=specimen_ids[0] if specimen_ids else None,
                    specimen_ids=specimen_ids or [],
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
                    "emits": ["START_RUN"],
                    "violations": violations,
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                },
            )
        if action_type == "START_RUN_OVERRIDE":
            # Co-location: agent must be in device zone (GS-019)
            device_id = args.get("device_id")
            agent_id = str(event.get("agent_id", ""))
            if device_id and self._zones is not None:
                device_zone = self._device_zone.get(str(device_id))
                agent_zone = self._zones.get_agent_zone(agent_id) if agent_id else None
                if device_zone and agent_zone is not None and agent_zone != device_zone:
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": RC_DEVICE_NOT_COLOCATED,
                        "violations": [
                            {"invariant_id": "INV-ZONE-002", "status": "VIOLATION"},
                        ],
                        "hashchain": hashchain_dict,
                    }
            specimen_ids = self._specimens.resolve_to_specimen_ids(
                args.get("specimen_ids"),
                args.get("aliquot_ids"),
            )
            if specimen_ids and token_refs:
                for tid in token_refs:
                    v = self._tokens.validity_violation(tid, t_s)
                    if v:
                        hashchain_dict, _ = self._audit.append(event)
                        return {
                            **base,
                            "status": "BLOCKED",
                            "emits": [],
                            "blocked_reason_code": TIME_EXPIRED,
                            "violations": [{"invariant_id": v, "status": "VIOLATION"}],
                            "hashchain": hashchain_dict,
                        }
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
                        "token_consumed": list(token_refs) if specimen_ids and token_refs else [],
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
                    "token_consumed": list(token_refs) if specimen_ids and token_refs else [],
                    "violations": [],
                    "hashchain": hashchain_dict,
                },
            )
        if action_type == "QC_EVENT":
            device_id = args.get("device_id")
            qc_outcome = args.get("qc_outcome", "pass")
            if device_id:
                self._qc.set_device_qc_state(str(device_id), str(qc_outcome))
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["QC_EVENT"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        if action_type == "GENERATE_RESULT":
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
                if analyte_code is not None and value is not None:
                    crit = self._critical.classify_and_set(
                        str(result_id), str(analyte_code), value, str(units)
                    )
                    if self._system_state.get("downtime_active") and crit != "none":
                        self._critical.set_notification_mode_required(
                            str(result_id), "phone_or_bleep"
                        )
            hashchain_dict, chain_broken = self._audit.append(event)
            emits_list = ["GENERATE_RESULT"]
            if args.get("analyte_code"):
                emits_list.append("CLASSIFY_RESULT")
            if result_id and self._critical.result_criticality(str(result_id)) != "none":
                if self._system_state.get("downtime_active"):
                    emits_list.append("NOTIFY_CRITICAL_RESULT")
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": emits_list,
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        if action_type == "RELEASE_RESULT":
            result_id = args.get("result_id")
            if result_id:
                rid = str(result_id)
                crit = self._critical.result_criticality(rid)
                if crit in ("CRIT_A", "CRIT_B") and not self._critical.has_ack(rid):
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": CRIT_NO_ACK,
                        "violations": [
                            {"invariant_id": "INV-CRIT-002", "status": "VIOLATION"},
                        ],
                        "hashchain": hashchain_dict,
                    }
                can_release, blocked_code = self._qc.can_release_result(rid)
                if not can_release and blocked_code == QC_FAIL_ACTIVE:
                    self._qc.hold_result(rid)
                    hashchain_dict, _ = self._audit.append(event)
                    return {
                        **base,
                        "status": "BLOCKED",
                        "emits": [],
                        "blocked_reason_code": QC_FAIL_ACTIVE,
                        "hashchain": hashchain_dict,
                    }
                self._qc.release_result(rid)
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["RELEASE_RESULT"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        if action_type == "HOLD_RESULT":
            result_id = args.get("result_id")
            if result_id:
                self._qc.hold_result(str(result_id))
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["HOLD_RESULT"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        if action_type == "RERUN_REQUEST":
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["RERUN_REQUEST"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        if action_type == "RELEASE_RESULT_OVERRIDE":
            result_id = args.get("result_id")
            if result_id and token_refs:
                for tid in token_refs:
                    v = self._tokens.validity_violation(tid, t_s)
                    if v:
                        hashchain_dict, _ = self._audit.append(event)
                        return {
                            **base,
                            "status": "BLOCKED",
                            "emits": [],
                            "blocked_reason_code": QC_FAIL_ACTIVE,
                            "violations": [{"invariant_id": v, "status": "VIOLATION"}],
                            "hashchain": hashchain_dict,
                        }
                for tid in token_refs:
                    self._tokens.consume_token(tid)
                self._qc.release_result_override_with_drift_flag(str(result_id))
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "token_consumed": list(token_refs) if result_id and token_refs else [],
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["RELEASE_RESULT"],
                "blocked_reason_code": None,
                "token_consumed": list(token_refs) if result_id and token_refs else [],
                "hashchain": hashchain_dict,
            }
        if action_type == "NOTIFY_CRITICAL_RESULT":
            result_id = args.get("result_id")
            channel = args.get("channel", "")
            receiver_role = args.get("receiver_role", "")
            agent_id = event.get("agent_id", "")
            if result_id:
                self._critical.record_notify(
                    str(result_id), channel, receiver_role, str(agent_id), t_s
                )
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["NOTIFY_CRITICAL_RESULT"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        if action_type == "ACK_CRITICAL_RESULT":
            result_id = args.get("result_id")
            agent_id = event.get("agent_id", "")
            if result_id:
                self._critical.record_ack(
                    str(result_id), args, str(agent_id), t_s
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
            return self._finalize_step(
                event,
                {
                    **base,
                    "status": "ACCEPTED",
                    "emits": ["ACK_CRITICAL_RESULT"],
                    "violations": [],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                },
            )
        if action_type == "ESCALATE_CRITICAL_RESULT":
            hashchain_dict, chain_broken = self._audit.append(event)
            if chain_broken:
                self._system_state["log_frozen"] = True
                self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
                return {
                    **base,
                    "status": "ACCEPTED",
                    "emits": [FORENSIC_FREEZE_LOG],
                    "blocked_reason_code": None,
                    "hashchain": hashchain_dict,
                }
            return {
                **base,
                "status": "ACCEPTED",
                "emits": ["ESCALATE_CRITICAL_RESULT"],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }

        # Default: append to audit, ACCEPTED
        hashchain_dict, chain_broken = self._audit.append(event)
        if chain_broken:
            self._system_state["log_frozen"] = True
            self._system_state["last_reason_code_system"] = AUDIT_CHAIN_BROKEN
            return {
                **base,
                "status": "ACCEPTED",
                "emits": [FORENSIC_FREEZE_LOG],
                "blocked_reason_code": None,
                "hashchain": hashchain_dict,
            }
        return {
            **base,
            "status": "ACCEPTED",
            "emits": [action_type] if action_type else [],
            "blocked_reason_code": None,
            "hashchain": hashchain_dict,
        }

    def query(self, expr: str) -> Any:
        """
        Query state for runner state_assertions.
        Supports: system_state('log_frozen'), last_reason_code_system, token_active.
        """
        expr = expr.strip()
        if expr == "last_reason_code_system":
            return self._system_state.get("last_reason_code_system")
        if expr.startswith("system_state(") and "log_frozen" in expr:
            return "true" if self._system_state.get("log_frozen", False) else "false"
        if "token_active" in expr or expr == "token_active":
            return self._tokens.list_active_ids()
        zone_state_match = re.match(r"zone_state\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", expr)
        if zone_state_match and self._zones is not None:
            return self._zones.zone_state(zone_state_match.group(1))
        specimen_status_match = re.match(r"specimen_status\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", expr)
        if specimen_status_match and self._specimens is not None:
            return self._specimens.specimen_status(specimen_status_match.group(1))
        last_reason_match = re.match(r"last_reason_code\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", expr)
        if last_reason_match and self._specimens is not None:
            return self._specimens.last_reason_code(last_reason_match.group(1))
        result_status_match = re.match(
            r"result_status\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", expr
        )
        if result_status_match and self._qc is not None:
            return self._qc.result_status(result_status_match.group(1))
        result_flags_match = re.match(
            r"result_flags\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", expr
        )
        if result_flags_match and self._qc is not None:
            return self._qc.result_flags(result_flags_match.group(1))
        result_crit_match = re.match(
            r"result_criticality\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", expr
        )
        if result_crit_match and self._critical is not None:
            return self._critical.result_criticality(result_crit_match.group(1))
        comm_exists_match = re.match(
            r"comm_record_exists\s*\(\s*result_id\s*=\s*['\"]([^'\"]+)['\"]\s*\)",
            expr,
        )
        if comm_exists_match and self._critical is not None:
            return "true" if self._critical.comm_record_exists(comm_exists_match.group(1)) else "false"
        notif_mode_match = re.match(
            r"notification_mode_required\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", expr
        )
        if notif_mode_match and self._critical is not None:
            return self._critical.notification_mode_required(
                notif_mode_match.group(1)
            )
        queue_head_match = re.match(
            r"queue_head\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", expr
        )
        if queue_head_match and self._queues is not None:
            return self._queues.queue_head(queue_head_match.group(1))
        queue_length_match = re.match(
            r"queue_length\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", expr
        )
        if queue_length_match and self._queues is not None:
            return self._queues.queue_length(queue_length_match.group(1))
        agent_zone_match = re.match(
            r"agent_zone\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", expr
        )
        if agent_zone_match and self._zones is not None:
            return self._zones.get_agent_zone(agent_zone_match.group(1))
        door_state_match = re.match(
            r"door_state\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", expr
        )
        if door_state_match and self._zones is not None:
            door_id = door_state_match.group(1)
            is_open, open_since_ts = self._zones.get_door_state(door_id)
            duration_s = (
                (self._now_ts - open_since_ts) if (open_since_ts is not None) else 0
            )
            return {"open": is_open, "open_since_ts": open_since_ts, "open_duration_s": duration_s}
        if expr == "specimen_counts" and self._specimens is not None:
            return self._specimens.get_status_counts()
        device_qc_match = re.match(
            r"device_qc_state\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", expr
        )
        if device_qc_match and self._qc is not None:
            return self._qc.device_qc_state(device_qc_match.group(1))
        device_state_match = re.match(
            r"device_state\s*\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", expr
        )
        if device_state_match and self._device_store is not None:
            return self._device_store.device_state(device_state_match.group(1))
        raise ValueError(f"Unsupported query: {expr!r}")
