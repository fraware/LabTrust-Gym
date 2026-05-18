"""PCSWorkflow domain-neutral interface."""

from __future__ import annotations

import inspect
from pathlib import Path

from labtrust_gym.pcs.workflows import PCSWorkflow, QcReleaseWorkflow


def test_pcs_workflow_exposes_required_methods() -> None:
    required = (
        "generate_runtime_artifacts",
        "emit_runtime_to_certificate_handoff",
        "attach_certificate",
        "emit_bundle_to_verifier_handoff",
        "emit_component_release_fragment",
        "generate_failure_case",
    )
    for name in required:
        assert hasattr(PCSWorkflow, name)
        assert callable(getattr(PCSWorkflow, name))


def test_qc_release_implements_execute_runtime(repo_root: Path) -> None:
    wf = QcReleaseWorkflow(policy_root=repo_root)
    assert wf.workflow_id == wf.profile.workflow_id
    assert wf.profile_path.is_file()
    sig = inspect.signature(wf.generate_failure_case)
    assert "failure_id" in sig.parameters
    assert "out_dir" in sig.parameters
