"""PCS claim and bundle status transition rules (Phase 2)."""

from __future__ import annotations

from typing import Any

from pcs_core.status import ArtifactStatus

PENDING_CLAIM_STATUS = ArtifactStatus.RUNTIME_OBSERVED.value
CERTIFIED_CLAIM_STATUS = ArtifactStatus.CERTIFICATE_CHECKED.value
PF_VERIFIED_STATUS = ArtifactStatus.PROOF_CHECKED.value
STALE_STATUS = ArtifactStatus.STALE.value

# LabTrust-owned claim_artifact transitions (ProofChecked is set only by Provability Fabric).
LABTRUST_CLAIM_TRANSITIONS: dict[str, frozenset[str]] = {
    PENDING_CLAIM_STATUS: frozenset(
        {CERTIFIED_CLAIM_STATUS, STALE_STATUS, ArtifactStatus.REJECTED.value}
    ),
    CERTIFIED_CLAIM_STATUS: frozenset({STALE_STATUS, ArtifactStatus.REJECTED.value}),
}


def assert_claim_status_transition(from_status: str, to_status: str, *, context: str = "claim_artifact") -> None:
    """Raise when ``to_status`` is not allowed from ``from_status`` for LabTrust workflows."""
    if from_status == PENDING_CLAIM_STATUS and to_status == PF_VERIFIED_STATUS:
        raise ValueError(
            f"{context}: LabTrust cannot transition directly from RuntimeObserved to ProofChecked"
        )
    allowed = LABTRUST_CLAIM_TRANSITIONS.get(from_status)
    if allowed is None:
        raise ValueError(f"{context}: unknown from_status {from_status!r}")
    if to_status not in allowed:
        raise ValueError(
            f"{context}: illegal transition {from_status!r} -> {to_status!r} "
            f"(allowed: {sorted(allowed)})"
        )


def assert_pending_bundle_claim_status(bundle: dict[str, Any]) -> None:
    """Pending ScienceClaimBundle must have claim_artifact.status = RuntimeObserved."""
    status = bundle.get("claim_artifact", {}).get("status")
    if status != PENDING_CLAIM_STATUS:
        raise ValueError(
            f"pending bundle claim_artifact.status must be {PENDING_CLAIM_STATUS!r}, got {status!r}"
        )


def assert_certified_bundle_claim_status(bundle: dict[str, Any]) -> None:
    """Certified ScienceClaimBundle must have claim_artifact.status = CertificateChecked."""
    status = bundle.get("claim_artifact", {}).get("status")
    if status != CERTIFIED_CLAIM_STATUS:
        raise ValueError(
            f"certified bundle claim_artifact.status must be {CERTIFIED_CLAIM_STATUS!r}, got {status!r}"
        )


def assert_labtrust_never_emits_proof_checked(bundle: dict[str, Any], *, context: str = "bundle") -> None:
    """LabTrust export/attach paths must never set claim_artifact.status to ProofChecked."""
    status = bundle.get("claim_artifact", {}).get("status")
    if status == PF_VERIFIED_STATUS:
        raise ValueError(f"{context}: LabTrust must not emit claim_artifact.status ProofChecked")


def assert_verification_result_proof_checked(doc: dict[str, Any]) -> None:
    """After PF signing, VerificationResult.v0 must report ProofChecked."""
    status = doc.get("status")
    if status != PF_VERIFIED_STATUS:
        raise ValueError(f"verification_result.status must be {PF_VERIFIED_STATUS!r}, got {status!r}")


def mark_bundle_stale_if_trace_diverged(bundle: dict[str, Any], *, context: str = "bundle") -> None:
    """
    When a certificate is present but runtime receipt trace_hash diverged, mark claim Stale and raise.

    Call after certificate attach or when validating an existing certified bundle.
    """
    certificates = bundle.get("certificates") or []
    receipts = bundle.get("runtime_receipts") or []
    if not certificates or not receipts:
        return

    receipt_hash = receipts[0].get("trace_hash")
    cert_hash = certificates[0].get("trace_hash")
    if receipt_hash != cert_hash:
        claim = bundle.setdefault("claim_artifact", {})
        claim["status"] = STALE_STATUS
        raise ValueError(
            f"{context}: trace_hash diverged after certificate "
            f"(receipt={receipt_hash!r}, certificate={cert_hash!r}); claim marked Stale"
        )
