"""ScienceClaimBundle pending export."""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.pcs.assumption_set import _ASSUMPTIONS, MAIN_CLAIM_TEXT
from labtrust_gym.pcs.export import export_pcs_bundle
from labtrust_gym.pcs.validate import validate_pcs_artifact


def test_pending_bundle_structure(valid_run: Path, tmp_path: Path) -> None:
    out = tmp_path / "science_claim_bundle.pending.json"
    bundle = export_pcs_bundle(valid_run, out)
    validate_pcs_artifact(bundle)
    assert bundle["certificates"] == []
    claim = bundle["claim_artifact"]
    assert claim["status"] == "RuntimeObserved"
    assert claim["claim_kind"] == "protocol_safety_claim"
    assert claim["artifact_type"] == "ClaimArtifact.v0"
    assert claim["claim_text"] == MAIN_CLAIM_TEXT
    assert claim["certificate_refs"] == []
    assert claim["source_repo"] == "https://github.com/fraware/LabTrust-Gym"
    assert len(bundle["assumption_set"]["assumptions"]) == len(_ASSUMPTIONS)
    assert len(bundle["runtime_receipts"]) == 1
    assert bundle["evidence_bundle"]["bundle_id"]
