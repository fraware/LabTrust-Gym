"""LabTrust PCS status boundary checks for release artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pcs_core.status import ArtifactStatus

from labtrust_gym.pcs.status_transitions import (
    PENDING_CLAIM_STATUS,
    assert_certified_bundle_claim_status,
    assert_claim_status_transition,
    assert_labtrust_never_emits_proof_checked,
    assert_pending_bundle_claim_status,
    mark_bundle_stale_if_trace_diverged,
)
from labtrust_gym.pcs.workflow_profile import WorkflowProfileView, workflow_profile_view

REJECTED_STATUS = ArtifactStatus.REJECTED.value


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_profile_forbidden_transitions(profile: WorkflowProfileView) -> list[str]:
    """Ensure WorkflowProfile forbidden transitions are rejected by LabTrust policy."""
    checks: list[str] = []
    for rule in profile.status_policy.get("forbidden_transitions") or []:
        from_status = rule.get("from_status")
        to_status = rule.get("to_status")
        if not from_status or not to_status:
            continue
        try:
            assert_claim_status_transition(from_status, to_status, context="workflow_profile")
        except ValueError:
            checks.append(f"forbidden_{from_status}_to_{to_status}")
        else:
            raise ValueError(
                f"workflow profile forbids {from_status!r} -> {to_status!r} "
                f"but LabTrust allows it"
            )
    return checks


def assert_runtime_receipt_status_for_release(release_root: Path) -> list[str]:
    """Release runtime receipts must be RuntimeObserved on the success path (not failed demos)."""
    receipt = _load_json(release_root / "runtime_receipt.json")
    status = receipt.get("status")
    if status != PENDING_CLAIM_STATUS:
        raise ValueError(
            f"release runtime_receipt.status must be {PENDING_CLAIM_STATUS!r}, got {status!r}"
        )
    if receipt.get("run_outcome") == "failed":
        raise ValueError("release runtime_receipt.run_outcome must not be failed")
    return ["runtime_receipt_runtime_observed"]


def assert_release_bundle_status_policy(
    release_root: Path,
    *,
    profile: WorkflowProfileView | None = None,
) -> list[str]:
    """
    Enforce LabTrust status boundaries on committed release bundles.

    - pending: RuntimeObserved
    - certified: CertificateChecked (never ProofChecked)
    - trace divergence after certificate attach must surface as Stale when checked
    """
    release_root = release_root.resolve()
    from labtrust_gym.config import get_repo_root

    profile = profile or workflow_profile_view(policy_root=get_repo_root())
    checks: list[str] = []

    pending_path = release_root / "science_claim_bundle.pending.json"
    certified_path = release_root / "science_claim_bundle.certified.json"
    if not pending_path.is_file():
        raise FileNotFoundError("missing science_claim_bundle.pending.json")
    if not certified_path.is_file():
        raise FileNotFoundError("missing science_claim_bundle.certified.json")

    pending = _load_json(pending_path)
    certified = _load_json(certified_path)

    assert_pending_bundle_claim_status(pending)
    assert_labtrust_never_emits_proof_checked(pending, context="pending bundle")
    checks.append("pending_status_runtime_observed")

    assert_certified_bundle_claim_status(certified)
    assert_labtrust_never_emits_proof_checked(certified, context="certified bundle")
    checks.append("certified_status_certificate_checked")
    checks.append("certified_never_proof_checked")

    checks.extend(assert_profile_forbidden_transitions(profile))

    mark_bundle_stale_if_trace_diverged(certified, context="certified bundle")
    checks.append("certified_trace_hash_consistent")

    checks.extend(assert_runtime_receipt_status_for_release(release_root))

    return checks


def assert_failed_runtime_receipt(receipt: dict[str, Any], *, expected_reason: str | None = None) -> None:
    """Failed workflow outputs use RuntimeObserved receipt with run_outcome failed (not ProofChecked)."""
    status = receipt.get("status")
    if status not in (PENDING_CLAIM_STATUS, REJECTED_STATUS):
        raise ValueError(f"failed runtime receipt status must be RuntimeObserved or Rejected, got {status!r}")
    if receipt.get("run_outcome") != "failed":
        raise ValueError("failed workflow runtime_receipt.run_outcome must be failed")
    assert_labtrust_never_emits_proof_checked({"claim_artifact": {"status": status}}, context="failed receipt")
    if expected_reason and receipt.get("final_reason_code") != expected_reason:
        raise ValueError(
            f"final_reason_code expected {expected_reason!r}, got {receipt.get('final_reason_code')!r}"
        )


def check_release_status_policy(
    release_dir: Path,
    *,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    """Run status policy checks; return summary for CLI JSON output."""
    from labtrust_gym.config import get_repo_root

    profile = workflow_profile_view(profile_path, policy_root=get_repo_root())
    labels = assert_release_bundle_status_policy(release_dir, profile=profile)
    return {
        "status": "passed",
        "workflow_id": profile.workflow_id,
        "property_id": profile.property_id,
        "policy_id": profile.status_policy.get("policy_id"),
        "checks": labels,
    }
