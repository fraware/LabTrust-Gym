"""WorkflowProfile.v0 loading and LabTrust workflow-profile driver."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.hash import pcs_digest

DEFAULT_WORKFLOW_PROFILE_REL = Path("examples/pcs_qc_release/workflow_profile.v0.json")

# LabTrust handoff property_id is not a WorkflowProfile.v0 field; bind by profile workflow_id.
PROPERTY_ID_BY_PROFILE_WORKFLOW_ID: dict[str, str] = {
    "labtrust.qc_release_v0.1": "hospital_lab.qc_release",
}

HANDOFF_KIND_RUNTIME_TO_CERTIFICATE = "runtime_to_certificate"
HANDOFF_KIND_BUNDLE_TO_VERIFIER = "bundle_to_verifier"


@dataclass(frozen=True)
class WorkflowProfileView:
    """Resolved WorkflowProfile.v0 fields for LabTrust protocol production."""

    path: Path
    document: dict[str, Any]
    workflow_id: str
    property_id: str
    domain: str
    description: str
    runtime_artifacts: tuple[str, ...]
    certificate_artifacts: tuple[str, ...]
    handoff_sequence: tuple[str, ...]
    required_registry_entries: tuple[str, ...]
    failure_modes: tuple[str, ...]
    limitations_notice: str
    status_policy: dict[str, Any]

    @property
    def requires_runtime_to_certificate(self) -> bool:
        return HANDOFF_KIND_RUNTIME_TO_CERTIFICATE in self.handoff_sequence

    @property
    def requires_bundle_to_verifier(self) -> bool:
        return HANDOFF_KIND_BUNDLE_TO_VERIFIER in self.handoff_sequence


def default_workflow_profile_path(policy_root: Path | None = None) -> Path:
    return (policy_root or get_repo_root()) / DEFAULT_WORKFLOW_PROFILE_REL


def resolve_property_id(workflow_id: str) -> str:
    prop = PROPERTY_ID_BY_PROFILE_WORKFLOW_ID.get(workflow_id)
    if prop is None:
        raise ValueError(
            f"no LabTrust property_id binding for workflow_id {workflow_id!r}; "
            f"known: {list(PROPERTY_ID_BY_PROFILE_WORKFLOW_ID)}"
        )
    return prop


def load_workflow_profile(path: Path | None = None, *, policy_root: Path | None = None) -> dict[str, Any]:
    """Load and validate WorkflowProfile.v0 JSON."""
    profile_path = (path or default_workflow_profile_path(policy_root)).resolve()
    if not profile_path.is_file():
        raise FileNotFoundError(f"WorkflowProfile not found: {profile_path}")
    doc = json.loads(profile_path.read_text(encoding="utf-8"))
    assert_workflow_profile_valid(doc)
    return doc


def assert_workflow_profile_valid(doc: dict[str, Any]) -> None:
    """Validate against pcs-core WorkflowProfile.v0 schema."""
    from pcs_core.validate import validate_artifact

    validate_artifact(doc)


def finalize_workflow_profile_digest(doc: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with ``signature_or_digest`` set from canonical content."""
    body = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    out = dict(body)
    out["signature_or_digest"] = pcs_digest(body)
    return out


def workflow_profile_view(
    path: Path | None = None,
    *,
    policy_root: Path | None = None,
) -> WorkflowProfileView:
    """Load profile and expose typed fields for generators."""
    profile_path = (path or default_workflow_profile_path(policy_root)).resolve()
    doc = load_workflow_profile(profile_path, policy_root=policy_root)
    workflow_id = str(doc["workflow_id"])
    return WorkflowProfileView(
        path=profile_path,
        document=doc,
        workflow_id=workflow_id,
        property_id=resolve_property_id(workflow_id),
        domain=str(doc["domain"]),
        description=str(doc["description"]),
        runtime_artifacts=tuple(doc["runtime_artifacts"]),
        certificate_artifacts=tuple(doc["certificate_artifacts"]),
        handoff_sequence=tuple(doc["handoff_sequence"]),
        required_registry_entries=tuple(doc["required_registry_entries"]),
        failure_modes=tuple(doc["failure_modes"]),
        limitations_notice=str(doc["limitations_notice"]),
        status_policy=dict(doc["status_policy"]),
    )


def handoff_id_for_kind(profile: WorkflowProfileView, kind: str) -> str:
    """Derive stable handoff_id values from ``workflow_id`` (profile-driven metadata)."""
    slug = profile.workflow_id.replace(".", "-")
    if kind == HANDOFF_KIND_RUNTIME_TO_CERTIFICATE:
        return f"handoff-{slug}-runtime-to-certifyedge"
    if kind == HANDOFF_KIND_BUNDLE_TO_VERIFIER:
        return f"handoff-{slug}-to-pf"
    raise ValueError(f"unsupported handoff kind for id derivation: {kind!r}")


def assert_workflow_profile_registry_check(path: Path) -> None:
    import subprocess

    proc = subprocess.run(
        ["pcs", "registry", "check-artifact", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ValueError(f"WorkflowProfile registry check failed: {proc.stderr or proc.stdout}")
