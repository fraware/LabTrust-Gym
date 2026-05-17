"""End-to-end handoff bundle export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.handoff import export_handoff_bundle

pytest.importorskip("pcs_core")


def test_export_handoff_bundle(tmp_path: Path, repo_root: Path) -> None:
    out = tmp_path / "handoff"
    manifest = export_handoff_bundle(out, policy_root=repo_root, work_dir=tmp_path / "work")
    assert (out / "certifyedge" / "valid_trace.json").is_file()
    assert (out / "certifyedge" / "invalid_missing_qc_trace.json").is_file()
    assert (out / "provability_fabric" / "science_claim_bundle.pending.json").is_file()
    assert manifest["provability_fabric"]["claim_id"] == "claim-pcs-qc-release-v0.1"
    pending = json.loads((out / "provability_fabric" / "science_claim_bundle.pending.json").read_text(encoding="utf-8"))
    assert pending["certificates"] == []
