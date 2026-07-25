"""Immutable declarative env/verifier mutation system (LT-VA-06)."""

from __future__ import annotations

import copy
import hashlib
from typing import Any, Mapping

from labtrust_gym.util.json_utils import canonical_json

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"

ENV_DIMENSIONS = (
    "device_failure",
    "transport_delay",
    "specimen_arrival",
    "key_revocation_timing",
    "staffing",
    "network_partition",
    "qc_drift",
    "multi_site_routing",
    "concurrency",
    "delayed_outcomes",
)

VERIFIER_DIMENSIONS = (
    "included_checks",
    "process_constraints",
    "authority_constraints",
    "side_effect_constraints",
    "penalty_weights",
    "state_visibility",
    "test_coverage",
    "abstention_threshold",
)


class MutationError(ValueError):
    """Fail-closed mutation error."""


def compute_mutation_digest(profile: Mapping[str, Any]) -> str:
    body = {k: v for k, v in profile.items() if k != "mutation_digest"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def validate_mutation_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    required = (
        "schema_id",
        "mutation_id",
        "source_profile_id",
        "target",
        "dimension",
        "operations",
        "rationale",
        "expected_effect",
        "production_prohibition",
        "claim_boundary",
    )
    if not isinstance(profile, dict):
        raise MutationError("mutation profile must be an object")
    for key in required:
        if key not in profile:
            raise MutationError(f"missing field: {key}")
    if profile["schema_id"] != "MutationProfile.v1":
        raise MutationError("schema_id must be MutationProfile.v1")
    if profile["claim_boundary"] != CLAIM_BOUNDARY:
        raise MutationError("claim_boundary mismatch")
    target = profile["target"]
    dim = profile["dimension"]
    if target == "env":
        if dim not in ENV_DIMENSIONS:
            raise MutationError(f"unsupported env dimension: {dim}")
    elif target == "verifier":
        if dim not in VERIFIER_DIMENSIONS:
            raise MutationError(f"unsupported verifier dimension: {dim}")
    else:
        raise MutationError(f"unsupported mutation target: {target}")
    if not isinstance(profile["operations"], list) or not profile["operations"]:
        raise MutationError("operations must be a non-empty list")
    if not isinstance(profile["production_prohibition"], bool):
        raise MutationError("production_prohibition must be bool")
    out = copy.deepcopy(dict(profile))
    digest = compute_mutation_digest(out)
    declared = out.get("mutation_digest")
    if declared is not None and declared != digest:
        raise MutationError("mutation_digest mismatch; immutable fail-closed")
    out["mutation_digest"] = digest
    return out


def map_risk_injector_to_mutation(
    injection_id: str,
    *,
    source_profile_id: str,
    dimension: str = "network_partition",
    rationale: str,
    expected_effect: str,
) -> dict[str, Any]:
    """
    Map an existing security risk injector id into a declarative VA mutation.
    Does not silently treat injectors as VA mutations without digests.
    """
    return validate_mutation_profile(
        {
            "schema_id": "MutationProfile.v1",
            "mutation_id": f"mut-from-injector:{injection_id}",
            "source_profile_id": source_profile_id,
            "target": "env",
            "dimension": dimension,
            "operations": [
                {
                    "op": "apply_risk_injector",
                    "injection_id": injection_id,
                    "requires_digest": True,
                }
            ],
            "rationale": rationale,
            "expected_effect": expected_effect,
            "production_prohibition": True,
            "claim_boundary": CLAIM_BOUNDARY,
            "mapped_from_risk_injector": injection_id,
        }
    )


def apply_mutation_to_state(
    state: dict[str, Any],
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply declarative ops to a state dict copy. Unsupported ops fail closed."""
    validated = validate_mutation_profile(profile)
    out = copy.deepcopy(state)
    for op in validated["operations"]:
        kind = op.get("op")
        if kind == "set_path":
            path = str(op["path"]).split(".")
            cur = out
            for p in path[:-1]:
                cur = cur.setdefault(p, {})
            cur[path[-1]] = copy.deepcopy(op["value"])
        elif kind == "flag_process_invalid":
            out.setdefault("process", {})["invalid_process"] = True
            out["process"]["invalid_process_reason"] = op.get("reason", "mutation")
        elif kind == "qc_drift":
            out.setdefault("qc", {}).setdefault("device_qc_state", {})[op.get("device_id", "D1")] = "fail"
        elif kind == "revoke_key_at":
            out.setdefault("authorization", {})["key_revoked_at"] = int(op["ts"])
            out["authorization"]["revoked_key_id"] = op.get("key_id")
        elif kind == "add_verifier_check":
            checks = out.setdefault("verifier", {}).setdefault("checks", [])
            checks.append(copy.deepcopy(op["check"]))
        elif kind == "set_abstention_threshold":
            out.setdefault("verifier", {})["abstention_threshold"] = float(op["value"])
        elif kind == "apply_risk_injector":
            injection_id = str(op["injection_id"])
            # Bind to real security injector registry (digest-bearing VA mutation).
            try:
                from labtrust_gym.security.risk_injections import make_injector
            except ImportError as exc:
                raise MutationError("risk injector module unavailable") from exc
            try:
                injector = make_injector(injection_id)
            except Exception as exc:  # noqa: BLE001 — fail closed on unknown ids
                raise MutationError(f"unsupported risk injector: {injection_id}") from exc
            out.setdefault("mutations_applied", []).append(
                {
                    "injection_id": injection_id,
                    "injector_class": type(injector).__name__,
                    "mutation_digest": validated["mutation_digest"],
                    "applied": True,
                }
            )
            # Stylized state effect for offline campaigns (injector mutates obs/actions at runtime).
            out.setdefault("security", {}).setdefault("injections", []).append(
                {
                    "injection_id": injection_id,
                    "mutation_digest": validated["mutation_digest"],
                }
            )
        else:
            raise MutationError(f"unsupported mutation operation: {kind}")
    out.setdefault("mutation_digests", []).append(validated["mutation_digest"])
    return out


def enforce_production_prohibition_for_release(
    profiles: list[Mapping[str, Any]],
    *,
    release_export: bool,
) -> None:
    """Release export must refuse production_prohibition=False mutations that are research-only... 
    Actually: production_prohibition=True means MUST NOT ship to production.
    Release packs for VA research may include them but must flag; production release fails closed.
    """
    if not release_export:
        return
    for p in profiles:
        validated = validate_mutation_profile(p)
        if validated["production_prohibition"] is not True:
            # Research mutations must be marked production_prohibition=True
            raise MutationError(
                f"mutation {validated['mutation_id']} missing production_prohibition=True for release"
            )
