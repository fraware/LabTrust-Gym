"""EnvironmentProfile.v1 loader with digest binding and fail-closed validation."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.errors import PolicyLoadError
from labtrust_gym.policy.loader import load_json, validate_against_schema
from labtrust_gym.util.json_utils import canonical_json

SCHEMA_ID = "EnvironmentProfile.v1"
CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "policy"
    / "schemas"
    / "verifier_assurance"
    / "EnvironmentProfile.v1.schema.json"
)


class EnvironmentProfileError(ValueError):
    """Fail-closed EnvironmentProfile validation error."""


def _schema() -> dict[str, Any]:
    return load_json(_SCHEMA_PATH)


def compute_profile_digest(profile: dict[str, Any]) -> str:
    """Digest excluding optional profile_digest field itself."""
    body = {k: v for k, v in profile.items() if k != "profile_digest"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def validate_environment_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Validate against schema; reject unknown fields; bind digest."""
    if not isinstance(profile, dict):
        raise EnvironmentProfileError("EnvironmentProfile must be an object")
    try:
        validate_against_schema(profile, _schema(), path=_SCHEMA_PATH)
    except PolicyLoadError as exc:
        raise EnvironmentProfileError(str(exc)) from exc
    if profile.get("schema_id") != SCHEMA_ID:
        raise EnvironmentProfileError(f"schema_id must be {SCHEMA_ID}")
    if profile.get("claim_boundary") != CLAIM_BOUNDARY:
        raise EnvironmentProfileError("claim_boundary mismatch; fail closed")
    digests = profile.get("policy_digests") or {}
    if not digests.get("policy_fingerprint"):
        raise EnvironmentProfileError("missing policy_digests.policy_fingerprint")
    out = copy.deepcopy(profile)
    digest = compute_profile_digest(out)
    declared = out.get("profile_digest")
    if declared is not None and declared != digest:
        raise EnvironmentProfileError("profile_digest mismatch; fail closed")
    out["profile_digest"] = digest
    return out


def load_environment_profile(path: Path | str) -> dict[str, Any]:
    """Load, validate, and return an EnvironmentProfile.v1 document."""
    path = Path(path)
    if not path.exists():
        raise EnvironmentProfileError(f"EnvironmentProfile not found: {path}")
    try:
        data = load_json(path)
    except PolicyLoadError as exc:
        raise EnvironmentProfileError(str(exc)) from exc
    return validate_environment_profile(data)


def bind_pcs_identity_refs(
    profile: dict[str, Any],
    pcs_identity_refs: list[str],
) -> dict[str, Any]:
    """Attach PCS identity refs without inventing a second ID authority."""
    if not pcs_identity_refs:
        raise EnvironmentProfileError("pcs_identity_refs must be non-empty when binding")
    out = copy.deepcopy(profile)
    digests = dict(out.get("policy_digests") or {})
    digests["pcs_identity_refs"] = list(pcs_identity_refs)
    out["policy_digests"] = digests
    out.pop("profile_digest", None)
    return validate_environment_profile(out)


def hospital_lab_seed_profile(
    *,
    policy_fingerprint: str,
    calibration_fingerprint: str | None = None,
    partner_id: str | None = None,
    pcs_identity_refs: list[str] | None = None,
    public_verifier_digest: str = "0" * 64,
    hidden_verifier_digest: str = "1" * 64,
) -> dict[str, Any]:
    """Seed EnvironmentProfile for the hospital_lab family with explicit fidelity limits."""
    if not policy_fingerprint or len(policy_fingerprint) < 16:
        raise EnvironmentProfileError("policy_fingerprint required")
    profile: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "profile_id": "envprof-hospital-lab-v1",
        "environment_family": "hospital_lab",
        "environment_version": "0.2.0",
        "policy_digests": {
            "policy_fingerprint": policy_fingerprint,
            "calibration_fingerprint": calibration_fingerprint,
            "pcs_identity_refs": pcs_identity_refs
            or [
                "claim-pcs-qc-release-v0.1",
                "labtrust-pcs-qc-release-v0.1",
            ],
        },
        "domain_overlay": {
            "partner_id": partner_id,
            "overlay_id": "default" if partner_id is None else f"partner:{partner_id}",
        },
        "initial_state_generator": {
            "generator_id": "labtrust.benchmarks.tasks",
            "generator_version": "0.2.0",
            "params": {},
        },
        "rng_clock_model": {
            "rng_backend": "labtrust_gym.engine.rng.RNG",
            "clock_mode": "simulated",
            "default_seed": 0,
        },
        "observation_schema_version": "labtrust.obs.v0.2",
        "action_schema_version": "labtrust.action_contract.v0.2",
        "actor_roles": [
            "ACCESSIONER",
            "TECH",
            "SUPERVISOR",
            "COURIER",
            "SYSTEM",
        ],
        "verifier_profiles": [
            {
                "verifier_id": "V_public.hospital_lab.v1",
                "role": "public",
                "profile_digest": public_verifier_digest,
                "visible_state_paths": [
                    "specimens.status",
                    "qc.device_qc_state",
                    "tokens.state",
                    "audit.head_hash",
                ],
            },
            {
                "verifier_id": "V_hidden.hospital_lab.v1",
                "role": "hidden",
                "profile_digest": hidden_verifier_digest,
                "visible_state_paths": ["*"],
            },
        ],
        "snapshot_format": {
            "format_id": "CanonicalSnapshot",
            "version": "1",
        },
        "known_fidelity_limits": [
            "Blood-sciences lane simulation only; not a full LIS or middleware replica.",
            "Device failure and transport models are stylized and deterministic under seed.",
            "Partner overlays use approved aggregates only; no raw clinical records.",
            "Does not model patient outcomes or clinical decision validity.",
            "Causal attribution graphs are experimental research models, not legal findings.",
        ],
        "supported_task_families": [
            "qc_release",
            "throughput",
            "security_attack",
            "verifier_assurance",
        ],
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return validate_environment_profile(profile)


def dump_environment_profile(profile: dict[str, Any], path: Path | str) -> str:
    """Write validated profile JSON; return digest."""
    validated = validate_environment_profile(profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(validated["profile_digest"])
