"""WorkflowProfile.v0 driver tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("pcs_core")

from labtrust_gym.pcs.failure_gallery import _failure_case_specs
from labtrust_gym.pcs.hash import pcs_digest
from labtrust_gym.pcs.workflow_profile import (
    assert_workflow_profile_valid,
    load_workflow_profile,
    workflow_profile_view,
)


def test_workflow_profile_validates_against_pcs_core(repo_root: Path) -> None:
    path = repo_root / "examples/pcs_qc_release/workflow_profile.v0.json"
    doc = load_workflow_profile(path)
    assert doc["workflow_id"] == "labtrust.qc_release_v0.1"
    assert doc["signature_or_digest"].startswith("sha256:")


def test_workflow_profile_digest_matches_file(repo_root: Path) -> None:
    path = repo_root / "examples/pcs_qc_release/workflow_profile.v0.json"
    doc = load_workflow_profile(path)
    body = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    assert doc["signature_or_digest"] == pcs_digest(body)


def test_workflow_profile_drives_failure_modes(repo_root: Path) -> None:
    profile = workflow_profile_view(policy_root=repo_root)
    specs = _failure_case_specs(profile)
    assert len(specs) == len(profile.failure_modes)
    assert "placeholder_commit" in profile.failure_modes


def test_workflow_profile_view_property_binding(repo_root: Path) -> None:
    profile = workflow_profile_view(policy_root=repo_root)
    assert profile.property_id == "hospital_lab.qc_release"
    assert profile.requires_runtime_to_certificate
    assert profile.requires_bundle_to_verifier


def test_workflow_profile_drives_handoff_ids(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    from labtrust_gym.pcs.workflows import QcReleaseWorkflow

    wf = QcReleaseWorkflow(policy_root=repo_root)
    assert wf.handoff_policy.certifyedge_handoff_id == (
        "handoff-labtrust-qc_release_v0-1-runtime-to-certifyedge"
    )
    assert wf.handoff_policy.pf_handoff_id == "handoff-labtrust-qc_release_v0-1-to-pf"

    work = tmp_path / "handoff-work"
    shutil.copytree(release_dir, work, dirs_exist_ok=True)
    doc = wf.emit_handoff_to_certifyedge(work, policy_root=repo_root, release_mode=True)
    assert doc["handoff_id"] == wf.handoff_policy.certifyedge_handoff_id
    on_disk = json.loads((work / "handoff_to_certifyedge.json").read_text(encoding="utf-8"))
    assert on_disk["handoff_id"] == wf.handoff_policy.certifyedge_handoff_id
