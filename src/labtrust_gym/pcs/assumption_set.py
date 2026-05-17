"""AssumptionSet.v0 for the PCS QC-release demo claim."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.pcs.ids import ASSUMPTION_SET_ID, SOURCE_SPAN_REF
from labtrust_gym.pcs.provenance import base_provenance, normalize_timestamp, with_signature
from labtrust_gym.pcs.schema_version import assert_schema_version

MAIN_CLAIM_TEXT = (
    "A sample may be released only after accession, QC completion, analysis, "
    "authorization by a release-capable actor, and satisfaction of the required "
    "temporal protocol constraints."
)

_ASSUMPTIONS: list[tuple[str, str, str]] = [
    (
        "asm-simulation-semantics",
        "The LabTrust-Gym simulation semantics are the operational model for this demo.",
        "operational",
    ),
    (
        "asm-role-policy",
        "The role policy in policy/pcs/roles.yaml defines release authorization.",
        "policy",
    ),
    (
        "asm-trace-complete",
        "The exported trace is complete for the run.",
        "policy",
    ),
    (
        "asm-qc-success",
        "The QC event in the trace represents successful QC completion.",
        "operational",
    ),
    (
        "asm-research-only",
        "The demo is a research/simulation artifact, not a clinical deployment.",
        "domain",
    ),
]


def build_assumption_set(
    *,
    created_at: str,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    assumptions = [
        {
            "assumption_id": aid,
            "text": text,
            "kind": kind,
            "status": "RuntimeObserved",
            "source_span_refs": [SOURCE_SPAN_REF],
        }
        for aid, text, kind in _ASSUMPTIONS
    ]
    doc: dict[str, Any] = {
        "assumption_set_id": ASSUMPTION_SET_ID,
        **base_provenance(policy_root=policy_root),
        "created_at": normalize_timestamp(created_at),
        "assumptions": assumptions,
        "human_review_status": "approved",
        "status": "HumanReviewed",
    }
    signed = with_signature(doc)
    assert_schema_version(signed)
    return signed
