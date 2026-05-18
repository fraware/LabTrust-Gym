"""
LabTrust PCS Phase 2 protocol package producer (delegates to workflow abstraction).

Clean-run regeneration is implemented on ``PcsWorkflow.regenerate_protocol_package``;
this module re-exports artifact constants and thin wrappers for CLI compatibility.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.protocol_artifacts import (
    LABTRUST_PROTOCOL_CORE_ARTIFACTS,
    LABTRUST_PROTOCOL_HANDOFF_ARTIFACTS,
    LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS,
    ProtocolRegenerationResult,
    assert_protocol_package_complete,
)
from labtrust_gym.pcs.certifyedge_client import resolve_certifyedge_bin
from labtrust_gym.pcs.workflows.registry import default_workflow

# Back-compat alias for tests and scripts importing from this module.
_resolve_certifyedge_bin = resolve_certifyedge_bin


def regenerate_release_protocol(
    out_dir: Path,
    *,
    policy_root: Path | None = None,
    certifyedge_bin: str = "certifyedge",
    certifyedge_spec: Path | None = None,
    certifyedge_root: Path | None = None,
    pcs_core: Path | None = None,
    run_dir: Path | None = None,
    property_id: str | None = None,
    workflow_profile: Path | None = None,
) -> ProtocolRegenerationResult:
    """
    Generate the complete LabTrust PCS protocol package from a clean deterministic run.

    Delegates to the registered ``PcsWorkflow`` (WorkflowProfile-driven).
    """
    root = policy_root or get_repo_root()
    workflow = default_workflow(policy_root=root, profile_path=workflow_profile)
    if property_id is not None and property_id != workflow.handoff_policy.property_id:
        raise ValueError(
            f"property_id {property_id!r} != workflow profile "
            f"({workflow.handoff_policy.property_id!r})"
        )
    return workflow.regenerate_protocol_package(
        out_dir,
        certifyedge_bin=certifyedge_bin,
        certifyedge_spec=certifyedge_spec,
        certifyedge_root=certifyedge_root,
        pcs_core=pcs_core,
        run_dir=run_dir,
    )


def emit_protocol_package_from_release(
    release_dir: Path,
    *,
    policy_root: Path | None = None,
    property_id: str | None = None,
    workflow_profile: Path | None = None,
) -> dict:
    """Re-emit handoffs and fragment from an existing release tree (no CertifyEdge re-run)."""
    from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol

    root = policy_root or get_repo_root()
    workflow = default_workflow(policy_root=root, profile_path=workflow_profile)
    release_dir = release_dir.resolve()
    workflow.emit_handoff_to_certifyedge(release_dir, policy_root=root, release_mode=True)
    workflow.emit_handoff_to_pf(release_dir, policy_root=root, release_mode=True)
    fragment = workflow.emit_release_fragment(release_dir, policy_root=root)
    workflow.publish_workflow_profile(release_dir)
    checks = verify_release_protocol(release_dir, policy_root=root)
    return {
        "release_dir": str(release_dir),
        "checks": checks,
        "fragment_digest": fragment.get("signature_or_digest"),
    }
