"""Handoff bundle CertifyEdge traces match committed goldens."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import deterministic_mode
from labtrust_gym.pcs.handoff import export_handoff_bundle

pytest.importorskip("pcs_core")

EXPECTED = get_repo_root() / "examples" / "pcs_qc_release" / "expected"

TRACE_GOLDENS = (
    "valid_trace.json",
    "invalid_missing_qc_trace.json",
    "invalid_unauthorized_trace.json",
)


@pytest.mark.parametrize("filename", TRACE_GOLDENS)
def test_handoff_certifyedge_trace_matches_golden(tmp_path: Path, filename: str) -> None:
    if not (EXPECTED / filename).is_file():
        pytest.skip(f"missing golden {filename}")
    golden = json.loads((EXPECTED / filename).read_text(encoding="utf-8"))
    with deterministic_mode():
        out = tmp_path / "handoff"
        export_handoff_bundle(out, work_dir=tmp_path / "work")
        produced = json.loads((out / "certifyedge" / filename).read_text(encoding="utf-8"))
    assert produced == golden
