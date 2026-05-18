"""Regenerate complete LabTrust-side PCS protocol package (re-export from producer)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.pcs.regenerate_release_chain import compare_release_hashes_to_canonical
from labtrust_gym.pcs.protocol_summary import build_protocol_regeneration_summary
from labtrust_gym.pcs.release_protocol_producer import (
    ProtocolRegenerationResult,
    emit_protocol_package_from_release,
    regenerate_release_protocol as _regenerate_release_protocol,
)
from labtrust_gym.pcs.workflows.registry import default_workflow


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
) -> tuple[Path, list[str], dict[str, Any]]:
    """Generate the full LabTrust protocol package; returns ``(release_dir, checks, summary)``."""
    result = _regenerate_release_protocol(
        out_dir,
        policy_root=policy_root,
        certifyedge_bin=certifyedge_bin,
        certifyedge_spec=certifyedge_spec,
        certifyedge_root=certifyedge_root,
        pcs_core=pcs_core,
        run_dir=run_dir,
        property_id=property_id,
        workflow_profile=workflow_profile,
    )
    wf = default_workflow(policy_root=policy_root, profile_path=workflow_profile)
    summary = build_protocol_regeneration_summary(
        result,
        workflow_id=wf.spec.workflow_id,
        property_id=wf.handoff_policy.property_id,
    )
    summary["workflow_profile"] = str(wf.profile.path)
    return result.release_dir, result.checks, summary


def report_canonical_drift(
    release_dir: Path,
    canonical_dir: Path,
) -> dict[str, Any]:
    """
    Compare release hashes to pcs-core canonical fixtures.

    Returns ``{"matched": [...], "drift": None}`` on success, or drift details on mismatch.
    """
    release_dir = release_dir.resolve()
    canonical_dir = canonical_dir.resolve()
    try:
        matched = compare_release_hashes_to_canonical(release_dir, canonical_dir)
        return {"matched": matched, "drift": None}
    except ValueError as exc:
        return {"matched": [], "drift": str(exc)}


def emit_protocol_handoffs_from_release(
    release_dir: Path,
    *,
    policy_root: Path | None = None,
    property_id: str = "hospital_lab.qc_release",
) -> dict[str, Any]:
    """Re-emit handoffs and fragment from an existing release directory (release mode)."""
    return emit_protocol_package_from_release(
        release_dir,
        policy_root=policy_root,
        property_id=property_id,
    )
