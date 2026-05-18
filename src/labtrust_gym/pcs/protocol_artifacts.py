"""LabTrust PCS protocol package artifact names and completeness checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME
from labtrust_gym.pcs.release_fragment import LABTRUST_RELEASE_FRAGMENT_NAME

WORKFLOW_PROFILE_RELEASE_NAME = "workflow_profile.v0.json"

LABTRUST_PROTOCOL_CORE_ARTIFACTS: tuple[str, ...] = (
    "trace.json",
    "runtime_receipt.json",
    "science_claim_bundle.pending.json",
    "trace_certificate.json",
    "science_claim_bundle.certified.json",
)

LABTRUST_PROTOCOL_HANDOFF_ARTIFACTS: tuple[str, ...] = (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    LABTRUST_RELEASE_FRAGMENT_NAME,
    WORKFLOW_PROFILE_RELEASE_NAME,
)

LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS: tuple[str, ...] = (
    *LABTRUST_PROTOCOL_CORE_ARTIFACTS,
    *LABTRUST_PROTOCOL_HANDOFF_ARTIFACTS,
)


@dataclass(frozen=True)
class ProtocolRegenerationResult:
    """Outcome of a clean-run protocol regeneration."""

    release_dir: Path
    run_dir: Path
    checks: list[str] = field(default_factory=list)
    commits: dict[str, str] = field(default_factory=dict)


def assert_protocol_package_complete(release_dir: Path) -> None:
    """Raise when any required LabTrust protocol artifact is missing under ``release_dir``."""
    release_dir = release_dir.resolve()
    missing = [name for name in LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS if not (release_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"incomplete LabTrust protocol package; missing: {', '.join(missing)}")
