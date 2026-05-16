"""Build EvidenceBundle.v0 for PCS demo runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.pcs.ids import (
    ASSUMPTION_SET_ID,
    CLAIM_ARTIFACT_ID,
    EVIDENCE_BUNDLE_ID,
    receipt_id,
)
from labtrust_gym.pcs.provenance import base_provenance, normalize_timestamp, with_signature


def build_evidence_bundle(
    *,
    run_id: str,
    created_at: str,
    claim_digest: str,
    receipt_digest: str,
    certificate_refs: list[str],
    certificate_digests: dict[str, str],
    policy_root: Path | None = None,
) -> dict[str, Any]:
    artifact_hashes: dict[str, str] = {
        CLAIM_ARTIFACT_ID: claim_digest,
        receipt_id(run_id): receipt_digest,
    }
    artifact_hashes.update(certificate_digests)
    doc: dict[str, Any] = {
        "bundle_id": EVIDENCE_BUNDLE_ID,
        **base_provenance(policy_root=policy_root),
        "created_at": normalize_timestamp(created_at),
        "claim_refs": [CLAIM_ARTIFACT_ID],
        "assumption_set_refs": [ASSUMPTION_SET_ID],
        "runtime_receipt_refs": [receipt_id(run_id)],
        "certificate_refs": certificate_refs,
        "artifact_hashes": artifact_hashes,
    }
    return with_signature(doc)
