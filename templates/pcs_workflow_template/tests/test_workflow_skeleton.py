"""Skeleton tests for a new PCS workflow — enable after integrating into LabTrust-Gym."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# from your_package.pcs.workflows.template import TemplateWorkflow


@pytest.mark.skip(reason="Enable after copying template into src/ and registering workflow")
def test_workflow_profile_has_required_handoffs() -> None:
    profile_path = Path(__file__).resolve().parents[1] / "workflow_profile.v0.json"
    doc = json.loads(profile_path.read_text(encoding="utf-8"))
    kinds = {h["kind"] for h in doc.get("handoffs", [])}
    assert "runtime_to_certificate" in kinds
    assert "bundle_to_verifier" in kinds


@pytest.mark.skip(reason="Enable after TemplateWorkflow is registered")
def test_generate_runtime_artifacts_writes_core_files(tmp_path: Path) -> None:
    # wf = TemplateWorkflow(profile_path=...)
    # paths = wf.generate_runtime_artifacts(tmp_path / "work")
    # assert (tmp_path / "work" / "trace.json").is_file()
    pass
