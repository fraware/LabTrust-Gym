"""Independent review gate (LTG-PR8 / LTG-09).

Fail-closed checks for process materials and signed-approval eligibility.
Unsigned slots are valid in default CI. Claiming "scientifically reviewed"
requires three approved, signed reports. This gate does not clinically
validate LabTrust-Gym.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import PolicyLoadError, load_json, validate_against_schema

REGISTRY_REL = "benchmarks/reviews/review_registry.v1.json"
REPORT_SCHEMA_REL = "policy/schemas/independent_review_report.v1.schema.json"
REGISTRY_SCHEMA_REL = "policy/schemas/independent_review_registry.v1.schema.json"

REQUIRED_DOCS: tuple[str, ...] = (
    "docs/reviews/README.md",
    "docs/reviews/charter.md",
    "docs/reviews/invitation_template.md",
    "docs/reviews/protocol_and_checklist.md",
    "docs/reviews/signed_approval_gate.md",
)

REQUIRED_ROLE_IDS: frozenset[str] = frozenset(
    {
        "laboratory_workflow_expert",
        "safety_or_quality_specialist",
        "multi_agent_benchmark_reviewer",
    }
)

_CLINICAL_LIMITATION_MARKERS: tuple[str, ...] = (
    "clinically validated",
    "clinical validation",
    "not convert",
)


def _load_schema(root: Path, rel: str) -> dict[str, Any] | None:
    path = root / rel
    if not path.is_file():
        return None
    data = load_json(path)
    if not isinstance(data, dict):
        raise PolicyLoadError(path, "schema must be a JSON object")
    return data


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _limitations_acknowledge_non_clinical(limitations: Any) -> bool:
    if not isinstance(limitations, list) or not limitations:
        return False
    blob = " ".join(str(x).lower() for x in limitations)
    return any(m in blob for m in _CLINICAL_LIMITATION_MARKERS)


def _validate_unsigned_approval(report: dict[str, Any], path_label: str) -> list[str]:
    errors: list[str] = []
    approval = report.get("approval") or {}
    if not isinstance(approval, dict):
        return [f"{path_label}: approval must be an object"]
    if approval.get("signed") is not False:
        errors.append(f"{path_label}: unsigned report must have approval.signed=false")
    if _nonempty_str(approval.get("reviewer_name")):
        errors.append(f"{path_label}: unsigned report must keep reviewer_name empty")
    if _nonempty_str(approval.get("reviewer_affiliation")):
        errors.append(f"{path_label}: unsigned report must keep reviewer_affiliation empty")
    if approval.get("reviewed_at") is not None:
        errors.append(f"{path_label}: unsigned report must keep reviewed_at null")
    if approval.get("signature_ref") is not None:
        errors.append(f"{path_label}: unsigned report must keep signature_ref null")
    scope = report.get("scope") or {}
    if isinstance(scope, dict):
        for axis in ("scenario_plausibility", "hazard_coverage", "non_claims_language"):
            if scope.get(axis) != "not_reviewed":
                errors.append(
                    f"{path_label}: unsigned report scope.{axis} must be not_reviewed"
                )
    attestation = str(approval.get("attestation") or "")
    if "UNSIGNED" not in attestation.upper():
        errors.append(f"{path_label}: unsigned attestation must state UNSIGNED")
    return errors


def _validate_approved_approval(report: dict[str, Any], path_label: str) -> list[str]:
    errors: list[str] = []
    approval = report.get("approval") or {}
    if not isinstance(approval, dict):
        return [f"{path_label}: approval must be an object"]
    if approval.get("signed") is not True:
        errors.append(f"{path_label}: approved report must have approval.signed=true")
    if not _nonempty_str(approval.get("reviewer_name")):
        errors.append(f"{path_label}: approved report requires reviewer_name")
    if not _nonempty_str(approval.get("reviewer_affiliation")):
        errors.append(f"{path_label}: approved report requires reviewer_affiliation")
    if not _nonempty_str(approval.get("reviewed_at")):
        errors.append(f"{path_label}: approved report requires reviewed_at")
    if not _nonempty_str(approval.get("signature_ref")):
        errors.append(
            f"{path_label}: approved report requires signature_ref "
            "(do not fabricate; use a real evidence path or URI)"
        )
    if approval.get("conflicts_of_interest_disclosed") is not True:
        errors.append(
            f"{path_label}: approved report requires conflicts_of_interest_disclosed=true"
        )
    if report.get("checklist_completed") is not True:
        errors.append(f"{path_label}: approved report requires checklist_completed=true")
    if not _nonempty_str(report.get("findings_summary")):
        errors.append(f"{path_label}: approved report requires findings_summary")
    if not _limitations_acknowledge_non_clinical(report.get("limitations_acknowledged")):
        errors.append(
            f"{path_label}: limitations_acknowledged must state that review does not "
            "clinically validate the system"
        )
    scope = report.get("scope") or {}
    if isinstance(scope, dict):
        for axis in ("scenario_plausibility", "hazard_coverage", "non_claims_language"):
            val = scope.get(axis)
            if val in (None, "not_reviewed"):
                errors.append(
                    f"{path_label}: approved report scope.{axis} must not be not_reviewed"
                )
            if val == "blocked":
                errors.append(
                    f"{path_label}: scope.{axis}=blocked is incompatible with approval.status=approved"
                )
    return errors


def validate_report_approval_semantics(report: dict[str, Any], path_label: str) -> list[str]:
    """Semantic checks beyond JSON Schema for one review report."""
    errors: list[str] = []
    approval = report.get("approval")
    if not isinstance(approval, dict):
        return [f"{path_label}: approval must be an object"]
    status = approval.get("status")
    if status == "unsigned":
        errors.extend(_validate_unsigned_approval(report, path_label))
    elif status == "approved":
        errors.extend(_validate_approved_approval(report, path_label))
    elif status in ("rejected", "abstained"):
        if approval.get("signed") is True and not _nonempty_str(approval.get("signature_ref")):
            errors.append(
                f"{path_label}: signed rejected/abstained reports still need signature_ref"
            )
        if not _limitations_acknowledge_non_clinical(report.get("limitations_acknowledged")):
            errors.append(
                f"{path_label}: limitations_acknowledged must state non-clinical-validation"
            )
    else:
        errors.append(f"{path_label}: unknown approval.status={status!r}")
    return errors


def validate_independent_review_gate(root: Path) -> list[str]:
    """
    Validate independent-review materials and fail-closed claim flag.

    Empty list means success. Default tree with UNSIGNED slots and
    scientifically_reviewed_claim_allowed=false is expected to pass.
    """
    root = Path(root)
    errors: list[str] = []

    for rel in REQUIRED_DOCS:
        path = root / rel
        if not path.is_file():
            errors.append(f"{path}: required independent-review doc missing")

    registry_path = root / REGISTRY_REL
    report_schema = None
    registry_schema = None
    try:
        report_schema = _load_schema(root, REPORT_SCHEMA_REL)
        registry_schema = _load_schema(root, REGISTRY_SCHEMA_REL)
    except PolicyLoadError as e:
        errors.append(str(e))

    if report_schema is None:
        errors.append(f"{root / REPORT_SCHEMA_REL}: required schema missing")
    if registry_schema is None:
        errors.append(f"{root / REGISTRY_SCHEMA_REL}: required schema missing")
    if not registry_path.is_file():
        errors.append(f"{registry_path}: required review registry missing")
        return errors
    if report_schema is None or registry_schema is None:
        return errors

    try:
        registry = load_json(registry_path)
        if not isinstance(registry, dict):
            errors.append(f"{registry_path}: registry must be a JSON object")
            return errors
        validate_against_schema(registry, registry_schema, registry_path)
    except PolicyLoadError as e:
        errors.append(str(e))
        return errors

    roles = registry.get("required_roles") or []
    if not isinstance(roles, list):
        errors.append(f"{registry_path}: required_roles must be a list")
        return errors

    seen: set[str] = set()
    approved_roles: set[str] = set()
    for entry in roles:
        if not isinstance(entry, dict):
            errors.append(f"{registry_path}: required_roles entry must be an object")
            continue
        role_id = str(entry.get("role_id") or "")
        report_rel = str(entry.get("report_path") or "")
        if role_id in seen:
            errors.append(f"{registry_path}: duplicate role_id={role_id!r}")
        seen.add(role_id)
        if role_id not in REQUIRED_ROLE_IDS:
            errors.append(f"{registry_path}: unexpected role_id={role_id!r}")
        report_path = root / report_rel
        if not report_path.is_file():
            errors.append(f"{report_path}: report for role {role_id!r} missing")
            continue
        try:
            report = load_json(report_path)
            if not isinstance(report, dict):
                errors.append(f"{report_path}: report must be a JSON object")
                continue
            validate_against_schema(report, report_schema, report_path)
        except PolicyLoadError as e:
            errors.append(str(e))
            continue
        if report.get("role_id") != role_id:
            errors.append(
                f"{report_path}: role_id {report.get('role_id')!r} does not match "
                f"registry role {role_id!r}"
            )
        errors.extend(validate_report_approval_semantics(report, str(report_path)))
        approval = report.get("approval") if isinstance(report.get("approval"), dict) else {}
        if isinstance(approval, dict) and approval.get("status") == "approved":
            approved_roles.add(role_id)

    missing_roles = REQUIRED_ROLE_IDS - seen
    for role_id in sorted(missing_roles):
        errors.append(f"{registry_path}: missing required role_id={role_id!r}")

    claim_allowed = bool(registry.get("scientifically_reviewed_claim_allowed"))
    all_approved = approved_roles == REQUIRED_ROLE_IDS and not missing_roles
    if claim_allowed and not all_approved:
        errors.append(
            f"{registry_path}: scientifically_reviewed_claim_allowed=true is forbidden "
            "until all three roles have approval.status=approved with signed evidence "
            "(fail-closed; do not invent approvals)"
        )
    if all_approved and not claim_allowed:
        # Allowed: maintainers may keep the claim flag false even after approvals
        # until LTG-PR9 explicitly opts in. Not an error.
        pass

    return errors


def scientifically_reviewed_claim_allowed(root: Path) -> bool:
    """True only when registry flag is true and the independent-review gate is clean."""
    root = Path(root)
    errors = validate_independent_review_gate(root)
    if errors:
        return False
    registry = load_json(root / REGISTRY_REL)
    if not isinstance(registry, dict):
        return False
    return bool(registry.get("scientifically_reviewed_claim_allowed"))


def assert_scientifically_reviewed_claim_allowed(root: Path) -> None:
    """Raise PolicyLoadError unless LTG-PR9 may claim scientific review."""
    root = Path(root)
    registry_path = root / REGISTRY_REL
    errors = validate_independent_review_gate(root)
    if errors:
        raise PolicyLoadError(
            registry_path,
            "independent review gate failed:\n" + "\n".join(errors),
        )
    if not scientifically_reviewed_claim_allowed(root):
        raise PolicyLoadError(
            registry_path,
            "scientifically_reviewed_claim_allowed is false; "
            "LTG-PR9 must not describe the release as scientifically reviewed",
        )
