"""Stable PCS identifiers for the QC-release demo."""

from __future__ import annotations

SOURCE_SPAN_REF = "span-pcs-qc-release-v0.1"
ASSUMPTION_SET_ID = "as-pcs-qc-release-v0.1"
CLAIM_ARTIFACT_ID = "claim-pcs-qc-release-v0.1"
SCIENCE_BUNDLE_ID = "scb-pcs-qc-release-v0.1"
EVIDENCE_BUNDLE_ID = "evidence-pcs-qc-release-v0.1"
VERIFICATION_POLICY_ID = "labtrust-pcs-qc-release-v0.1"
FORMAL_STATEMENT = (
    "release_sample implies prior accession_sample, perform_qc, record_analysis, and release_capable actor_role"
)


def receipt_id(run_id: str) -> str:
    return f"receipt-{run_id}"
