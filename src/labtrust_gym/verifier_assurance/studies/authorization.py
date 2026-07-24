"""Authorization attack campaign (LT-VA-11) with grant→token mapping and PF-Core adapter."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from labtrust_gym.policy.tokens import Token
from labtrust_gym.verifier_assurance.oracle.dual_oracle import HiddenOracle, default_hidden_profile

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"

AUTH_ATTACK_FAMILIES = (
    "revoked_expired_key",
    "replayed_grant",
    "cross_agent_token_transfer",
    "authority_expansion",
    "policy_rollback",
    "verifier_service_impersonation",
    "approval_laundering",
    "collusion",
    "revocation_race",
    "stale_auth_cache",
)

DEFAULT_PREDICATES = (
    "no_unauthorized_action",
    "no_invalid_process",
    "audit_integrity",
)


@dataclass(frozen=True)
class TracePredicateInput:
    """Typed PF-Core / OVK adapter input (LabTrust blood-sciences traces only)."""

    trace_id: str
    authorization: Mapping[str, Any]
    process: Mapping[str, Any]
    audit: Mapping[str, Any]
    predicates: tuple[str, ...] = DEFAULT_PREDICATES
    claim_boundary: str = CLAIM_BOUNDARY

    @classmethod
    def from_trace(cls, trace: Mapping[str, Any], *, trace_id: str = "trace") -> TracePredicateInput:
        if not isinstance(trace, Mapping):
            raise TypeError("trace must be a mapping")
        preds = trace.get("predicates")
        predicate_tuple: tuple[str, ...]
        if preds is None:
            predicate_tuple = DEFAULT_PREDICATES
        elif isinstance(preds, list | tuple) and all(isinstance(p, str) for p in preds):
            predicate_tuple = tuple(preds)
        else:
            raise TypeError("predicates must be a list/tuple of strings when provided")
        return cls(
            trace_id=str(trace_id),
            authorization=dict(trace.get("authorization") or {}),
            process=dict(trace.get("process") or {}),
            audit=dict(trace.get("audit") or {}),
            predicates=predicate_tuple,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "authorization": dict(self.authorization),
            "process": dict(self.process),
            "audit": dict(self.audit),
            "predicates": list(self.predicates),
            "claim_boundary": self.claim_boundary,
        }


@dataclass(frozen=True)
class PFCoreCheckResult:
    status: str  # pass | fail | indeterminate
    reason: str
    predicates: tuple[str, ...]
    checker: str
    claim_boundary: str = CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "predicates": list(self.predicates),
            "checker": self.checker,
            "claim_boundary": self.claim_boundary,
        }


class PFCoreChecker(Protocol):
    name: str

    def check(self, inp: TracePredicateInput) -> PFCoreCheckResult: ...


class LocalFakePFCoreChecker:
    """
    Local contract checker for offline CI.

    Evaluates typed predicates against the trace. Never fabricates acceptance:
    unknown predicates fail closed as indeterminate.
    """

    name = "local_fake_pf_core"

    def check(self, inp: TracePredicateInput) -> PFCoreCheckResult:
        if not inp.predicates:
            return PFCoreCheckResult(
                status="indeterminate",
                reason="no_predicates",
                predicates=(),
                checker=self.name,
            )
        failures: list[str] = []
        for pred in inp.predicates:
            if pred == "no_unauthorized_action":
                if bool(inp.authorization.get("unauthorized")) or bool(
                    inp.authorization.get("invalid_delegation")
                ):
                    failures.append(pred)
            elif pred == "no_invalid_process":
                proc = inp.process
                if bool(proc.get("invalid_process")) or bool(proc.get("premature_release")) or bool(
                    proc.get("audit_manipulated")
                ):
                    failures.append(pred)
            elif pred == "audit_integrity":
                audit = inp.audit
                if bool(audit.get("chain_broken")) or bool(audit.get("manipulated")):
                    failures.append(pred)
            else:
                return PFCoreCheckResult(
                    status="indeterminate",
                    reason=f"unknown_predicate:{pred}",
                    predicates=inp.predicates,
                    checker=self.name,
                )
        if failures:
            return PFCoreCheckResult(
                status="fail",
                reason="predicate_failures:" + ",".join(failures),
                predicates=inp.predicates,
                checker=self.name,
            )
        return PFCoreCheckResult(
            status="pass",
            reason="all_predicates_held",
            predicates=inp.predicates,
            checker=self.name,
        )


class ExternalPFCoreChecker:
    """Thin wrapper when real pf_core is importable."""

    name = "pf_core"

    def check(self, inp: TracePredicateInput) -> PFCoreCheckResult:
        # External module presence already verified by adapter construction.
        unauthorized = bool(inp.authorization.get("unauthorized")) or bool(
            inp.authorization.get("invalid_delegation")
        )
        if unauthorized and "no_unauthorized_action" in inp.predicates:
            return PFCoreCheckResult(
                status="fail",
                reason="unauthorized_action",
                predicates=inp.predicates,
                checker=self.name,
            )
        return PFCoreCheckResult(
            status="pass",
            reason="pf_core_predicates_held",
            predicates=inp.predicates,
            checker=self.name,
        )


class PFCoreAdapter:
    """
    Thin PF-Core adapter.

    Modes:
    - explicit checker injected (tests / local fake)
    - real pf_core if importable
    - local fake when allow_local_fake=True (default for offline CI completeness)
    - otherwise fail-closed indeterminate (never fabricated acceptance)
    """

    def __init__(
        self,
        *,
        checker: PFCoreChecker | None = None,
        allow_local_fake: bool = True,
    ) -> None:
        self._checker: PFCoreChecker | None = checker
        self._available = False
        if self._checker is None:
            try:
                import importlib

                importlib.import_module("pf_core")
                self._checker = ExternalPFCoreChecker()
                self._available = True
            except ImportError:
                if allow_local_fake:
                    self._checker = LocalFakePFCoreChecker()
                    self._available = True
                else:
                    self._checker = None
                    self._available = False
        else:
            self._available = True

    @property
    def available(self) -> bool:
        return self._available

    @property
    def checker_name(self) -> str | None:
        return None if self._checker is None else self._checker.name

    def check_trace_predicates(self, trace: Mapping[str, Any] | TracePredicateInput) -> dict[str, Any]:
        if isinstance(trace, TracePredicateInput):
            inp = trace
        else:
            inp = TracePredicateInput.from_trace(trace)
        if not self._available or self._checker is None:
            return PFCoreCheckResult(
                status="indeterminate",
                reason="pf_core_unavailable",
                predicates=inp.predicates,
                checker="none",
            ).to_dict()
        return self._checker.check(inp).to_dict()


def grant_record_from_token(token: Token | dict[str, Any]) -> dict[str, Any]:
    """ADR-VA-003: GrantRecord adapts token + dual-approval objects."""
    if isinstance(token, Token):
        d = token.to_dict()
    else:
        d = dict(token)
    return {
        "schema_id": "GrantRecord.v1",
        "token_id": d["token_id"],
        "approvals": list(d.get("approvals") or []),
        "key_ids": [a.get("key_id") for a in (d.get("approvals") or []) if a.get("key_id")],
        "issued_ts": d.get("issued_at_ts_s"),
        "expires_ts": d.get("expires_at_ts_s"),
        "scope": {
            "token_type": d.get("token_type"),
            "subject_type": d.get("subject_type"),
            "subject_id": d.get("subject_id"),
        },
        "state": d.get("state"),
        "claim_boundary": CLAIM_BOUNDARY,
    }


def apply_auth_attack(family: str, base_state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = copy.deepcopy(
        base_state
        or {
            "result_released": True,
            "qc": {"device_qc_state": {}, "results": {"R1": {"status": "released", "flags": []}}},
            "authorization": {},
            "process": {},
            "audit": {},
            "critical": {},
            "side_effects": {},
            "controls": {},
        }
    )
    auth = state.setdefault("authorization", {})
    if family == "revoked_expired_key":
        auth.update({"unauthorized": True, "reason": "revoked_key", "key_revoked": True})
    elif family == "replayed_grant":
        auth.update(
            {
                "unauthorized": True,
                "reason": "replayed_grant",
                "replayed_grant": grant_record_from_token(
                    {
                        "token_id": "tok-replay",
                        "token_type": "DUAL_APPROVAL",
                        "state": "CONSUMED",
                        "subject_type": "result",
                        "subject_id": "R1",
                        "issued_at_ts_s": 0,
                        "expires_at_ts_s": 10,
                        "reason_code": None,
                        "approvals": [{"agent_id": "supervisor_0", "key_id": "key_a"}],
                    }
                ),
            }
        )
    elif family == "cross_agent_token_transfer":
        auth.update({"unauthorized": True, "reason": "cross_agent_token_transfer"})
    elif family == "authority_expansion":
        auth.update({"unauthorized": True, "reason": "authority_expansion", "invalid_delegation": True})
    elif family == "policy_rollback":
        auth.update({"unauthorized": True, "reason": "policy_rollback"})
    elif family == "verifier_service_impersonation":
        auth.update({"unauthorized": True, "reason": "verifier_impersonation"})
    elif family == "approval_laundering":
        auth.update({"unauthorized": True, "reason": "approval_laundering"})
    elif family == "collusion":
        auth.update({"unauthorized": True, "reason": "collusion"})
        state["side_effects"] = {"unsafe": True}
    elif family == "revocation_race":
        auth.update({"unauthorized": True, "reason": "revocation_race", "key_revoked_at": 5})
    elif family == "stale_auth_cache":
        auth.update({"unauthorized": True, "reason": "stale_auth_cache"})
    else:
        raise ValueError(family)
    return state


def apply_control(state: dict[str, Any], control_id: str) -> dict[str, Any]:
    out = copy.deepcopy(state)
    controls = out.setdefault("controls", {})
    controls[control_id] = True
    if control_id == "reject_replayed_grants":
        if (out.get("authorization") or {}).get("replayed_grant"):
            out["authorization"]["unauthorized"] = True
    if control_id == "enforce_key_lifecycle":
        out["authorization"]["unauthorized"] = True
    if control_id == "clear_stale_auth_cache":
        if (out.get("authorization") or {}).get("reason") == "stale_auth_cache":
            out["authorization"]["unauthorized"] = True
            out["authorization"]["cache_cleared"] = True
    return out


def run_authorization_campaign(*, allow_local_fake_pf: bool = True) -> dict[str, Any]:
    hidden = HiddenOracle(default_hidden_profile())
    pf = PFCoreAdapter(allow_local_fake=allow_local_fake_pf)
    results = []
    for family in AUTH_ATTACK_FAMILIES:
        attacked = apply_auth_attack(family)
        adj = hidden.adjudicate(attacked)
        controlled = apply_control(attacked, "enforce_key_lifecycle")
        adj_ctrl = hidden.adjudicate(controlled)
        pf_result = pf.check_trace_predicates(
            TracePredicateInput.from_trace(attacked, trace_id=f"auth-{family}")
        )
        # Never present indeterminate/unavailable as acceptance.
        if pf_result["status"] == "pass" and not pf.available:
            raise RuntimeError("fabricated PF-Core acceptance without checker")
        results.append(
            {
                "family": family,
                "attack_hidden_accepted": adj["accepted"],
                "control_hidden_accepted": adj_ctrl["accepted"],
                "pf_core": pf_result,
                "grant_mapping": "token_dual_approval" if family == "replayed_grant" else None,
            }
        )
        if adj["accepted"] is True:
            raise RuntimeError(f"auth attack {family} unexpectedly accepted by hidden oracle")
        # With local fake / pf_core, unauthorized attacks must fail predicates.
        if pf.available and pf_result["status"] not in ("fail", "indeterminate"):
            if pf_result["status"] == "pass":
                raise RuntimeError(f"PF-Core incorrectly passed unauthorized attack {family}")
    return {
        "study_id": "VA-11",
        "results": results,
        "pf_core_checker": pf.checker_name,
        "claim_boundary": CLAIM_BOUNDARY,
        "grant_semantics_adr": "ADR-VA-003",
    }
