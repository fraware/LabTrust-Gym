"""ScienceClaimBundle.v0 assembly for PCS demo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.assumption_set import build_assumption_set
from labtrust_gym.pcs.claim_artifact import build_claim_artifact
from labtrust_gym.pcs.evidence_bundle import build_evidence_bundle
from labtrust_gym.pcs.ids import SCIENCE_BUNDLE_ID, VERIFICATION_POLICY_ID
from labtrust_gym.pcs.provenance import base_provenance, normalize_timestamp, with_signature
from labtrust_gym.pcs.runtime_receipt import build_runtime_receipt
from labtrust_gym.pcs.schema_version import assert_science_claim_bundle_versions


def build_science_claim_bundle(
    run_dir: Path,
    *,
    policy_root: Path | None = None,
    certificates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    run_id = meta["run_id"]
    created_at = meta["ended_at"]
    receipt = build_runtime_receipt(run_dir, policy_root=policy_root)
    cert_list = list(certificates or [])
    cert_refs = [c["certificate_id"] for c in cert_list]
    claim_status = "CertificateChecked" if cert_list else "RuntimeObserved"
    assumptions = build_assumption_set(created_at=created_at, policy_root=policy_root)
    claim = build_claim_artifact(
        run_id=run_id,
        created_at=created_at,
        assumption_set_id=assumptions["assumption_set_id"],
        certificate_refs=cert_refs,
        status=claim_status,
        policy_root=policy_root,
    )
    cert_digests = {c["certificate_id"]: c["signature_or_digest"] for c in cert_list}
    evidence = build_evidence_bundle(
        run_id=run_id,
        created_at=created_at,
        claim_digest=claim["signature_or_digest"],
        receipt_digest=receipt["signature_or_digest"],
        certificate_refs=cert_refs,
        certificate_digests=cert_digests,
        policy_root=policy_root,
    )
    doc: dict[str, Any] = {
        "bundle_id": SCIENCE_BUNDLE_ID,
        **base_provenance(policy_root=policy_root),
        "created_at": normalize_timestamp(created_at),
        "claim_artifact": claim,
        "assumption_set": assumptions,
        "runtime_receipts": [receipt],
        "certificates": cert_list,
        "evidence_bundle": evidence,
        "verification_policy": {
            "policy_id": VERIFICATION_POLICY_ID,
            "required_checks": [
                "schema-valid",
                "trace-hash-alignment",
                "assumption-set-present",
            ],
        },
    }
    signed = with_signature(doc)
    assert_science_claim_bundle_versions(signed)
    return signed
