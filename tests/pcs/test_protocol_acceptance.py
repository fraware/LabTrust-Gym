"""
PCS protocol producer acceptance criteria (Phase 2 reference runtime).

Maps to the LabTrust reference-producer mission checklist.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pcs_core")

from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    assert_handoff_manifest_valid,
)
from labtrust_gym.pcs.release_fragment import assert_release_fragment_valid
from labtrust_gym.pcs.protocol_artifacts import WORKFLOW_PROFILE_RELEASE_NAME
from labtrust_gym.pcs.release_protocol_producer import (
    LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS,
    assert_protocol_package_complete,
)
from labtrust_gym.pcs.status_policy import check_release_status_policy
from labtrust_gym.pcs.status_transitions import assert_labtrust_never_emits_proof_checked
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol
from labtrust_gym.pcs.workflows import QcReleaseWorkflow, get_workflow_by_key


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_acceptance_committed_protocol_package_complete(release_dir: Path) -> None:
    assert_protocol_package_complete(release_dir)


def test_acceptance_handoffs_are_handoff_manifest_v0(release_dir: Path) -> None:
    for name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME):
        assert_handoff_manifest_valid(_load(release_dir / name))


def test_acceptance_release_fragment_is_component_release_fragment_v0(release_dir: Path) -> None:
    assert_release_fragment_valid(_load(release_dir / "labtrust_release_fragment.json"))


def test_acceptance_labtrust_never_emits_proof_checked(release_dir: Path) -> None:
    assert_labtrust_never_emits_proof_checked(_load(release_dir / "science_claim_bundle.pending.json"))
    assert_labtrust_never_emits_proof_checked(_load(release_dir / "science_claim_bundle.certified.json"))


def test_acceptance_status_policy_on_release(release_dir: Path) -> None:
    result = check_release_status_policy(release_dir)
    assert result["status"] == "passed"


def test_acceptance_release_includes_published_workflow_profile(release_dir: Path) -> None:
    profile_path = release_dir / WORKFLOW_PROFILE_RELEASE_NAME
    assert profile_path.is_file()
    from labtrust_gym.pcs.workflow_profile import load_workflow_profile

    doc = load_workflow_profile(profile_path)
    assert doc["workflow_id"] == "labtrust.qc_release_v0.1"


def test_acceptance_verify_release_protocol_on_fixtures(release_dir: Path) -> None:
    labels = verify_release_protocol(release_dir)
    assert "workflow_profile_schema" in labels
    assert "handoff_manifest_schema" in labels
    assert "status_transition_policy" in labels
    assert "no_mock_certificate" in labels


def test_acceptance_qc_workflow_abstraction(repo_root: Path) -> None:
    wf = get_workflow_by_key("hospital_lab.qc_release", policy_root=repo_root)
    assert isinstance(wf, QcReleaseWorkflow)
    assert wf.spec.workflow_id == "labtrust.qc_release_v0.1"
    assert wf.spec.property_id == "hospital_lab.qc_release"
    profile_path = repo_root / "examples/pcs_qc_release/workflow_profile.v0.json"
    assert profile_path.is_file()
    from labtrust_gym.pcs.workflow_profile import load_workflow_profile

    assert load_workflow_profile(profile_path)["workflow_id"] == wf.spec.workflow_id
    assert wf.spec.success_case
    assert wf.spec.expected_certificates
    assert wf.spec.limitations_notice


def test_acceptance_check_status_policy_cli(release_dir: Path, repo_root: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "check-status-policy",
            "--release-dir",
            str(release_dir),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_acceptance_all_protocol_artifact_names_documented() -> None:
    expected = {
        "trace.json",
        "runtime_receipt.json",
        "science_claim_bundle.pending.json",
        "trace_certificate.json",
        "science_claim_bundle.certified.json",
        HANDOFF_TO_CERTIFYEDGE_NAME,
        HANDOFF_TO_PF_NAME,
        "labtrust_release_fragment.json",
        WORKFLOW_PROFILE_RELEASE_NAME,
    }
    assert set(LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS) == expected
