"""ClaimArtifact.v0 for protocol safety claim."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.pcs.assumption_set import MAIN_CLAIM_TEXT
from labtrust_gym.pcs.ids import (
    CLAIM_ARTIFACT_ID,
    FORMAL_STATEMENT,
    SOURCE_SPAN_REF,
    receipt_id,
)
from labtrust_gym.pcs.provenance import base_provenance, normalize_timestamp, with_signature
from labtrust_gym.pcs.schema_version import assert_schema_version


def build_claim_artifact(
    *,
    run_id: str,
    created_at: str,
    assumption_set_id: str,
    certificate_refs: list[str],
    status: str = "RuntimeObserved",
    policy_root: Path | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "artifact_id": CLAIM_ARTIFACT_ID,
        "artifact_type": "ClaimArtifact.v0",
        **base_provenance(policy_root=policy_root),
        "created_at": normalize_timestamp(created_at),
        "status": status,
        "claim_text": MAIN_CLAIM_TEXT,
        "claim_kind": "protocol_safety_claim",
        "assumption_set_ref": assumption_set_id,
        "source_span_refs": [SOURCE_SPAN_REF],
        "formal_statement": FORMAL_STATEMENT,
        "certificate_refs": certificate_refs,
        "runtime_receipt_refs": [receipt_id(run_id)],
    }
    signed = with_signature(doc)
    assert_schema_version(signed)
    return signed
