"""PCS workflow abstraction (multi-workflow readiness)."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.workflows import QcReleaseWorkflow, default_workflow, get_workflow, registered_workflow_ids
from labtrust_gym.pcs.workflows.qc_release import DEMO_NAME


def test_qc_release_uses_workflow_abstraction(repo_root: Path) -> None:
    wf = get_workflow("qc_release", policy_root=repo_root)
    assert isinstance(wf, QcReleaseWorkflow)
    assert wf.spec.workflow_id == "labtrust.qc_release_v0.1"
    assert wf.spec.property_id == "hospital_lab.qc_release"
    assert wf.handoff_policy.property_id == "hospital_lab.qc_release"
    assert wf.spec.demo_name == DEMO_NAME
    assert wf.profile.path.is_file()
    assert wf.spec.success_case == "qc-release"
    assert wf.spec.expected_certificates == ("TraceCertificate.v0",)
    assert "ProofChecked" in wf.spec.limitations_notice
    assert "qc-release-invalid-missing-qc" in wf.spec.failure_cases
    assert callable(wf.trace_generator())
    assert callable(wf.runtime_receipt_generator())
    assert callable(wf.claim_bundle_generator())
    assert (repo_root / "examples" / "pcs_qc_release" / wf.spec.scenario_yaml).is_file()


def test_default_workflow_is_qc_release(repo_root: Path) -> None:
    assert default_workflow(policy_root=repo_root).spec.workflow_id == "labtrust.qc_release_v0.1"


def test_workflow_registry_lists_qc_release() -> None:
    assert "qc_release" in registered_workflow_ids()


@pytest.mark.parametrize(
    "alias",
    [
        "hospital_lab.qc_release",
        "qc_release",
        "labtrust_qc_release",
        "hospital_lab_qc_release",
    ],
)
def test_workflow_aliases_resolve_to_qc_release(alias: str, repo_root: Path) -> None:
    from labtrust_gym.pcs.workflows.registry import resolve_workflow_id

    assert resolve_workflow_id(alias) == "qc_release"
    assert get_workflow(alias, policy_root=repo_root).spec.property_id == "hospital_lab.qc_release"


def test_run_demo_delegates_to_workflow_trace_generator(
    repo_root: Path, tmp_path: Path
) -> None:
    out = tmp_path / "qc-release"
    run_dir = run_demo("qc-release", out_dir=out, policy_root=repo_root, deterministic=True)
    assert run_dir == out.resolve()
    assert (run_dir / "trace.json").is_file()
    assert (run_dir / "run_meta.json").is_file()


def test_workflow_export_protocol_inputs(tmp_path: Path, repo_root: Path) -> None:
    wf = QcReleaseWorkflow(policy_root=repo_root)
    run_dir = wf.trace_generator()(out_dir=tmp_path / "run", deterministic=True)
    work = tmp_path / "work"
    paths = wf.export_protocol_inputs(run_dir, work, policy_root=repo_root)
    assert paths["trace"].is_file()
    assert paths["runtime_receipt"].is_file()
    assert paths["pending_bundle"].is_file()
