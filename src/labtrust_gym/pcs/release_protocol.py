"""Phase 2 PCS protocol artifact guards for LabTrust ``release/``."""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_PF_NAME,
    assert_handoff_manifest_valid,
)
from labtrust_gym.pcs.release_fragment import (
    LABTRUST_RELEASE_FRAGMENT_NAME,
    assert_release_fragment_source_commit_matches_artifacts,
    assert_release_fragment_valid,
)

LEGACY_PF_HANDOFF_NAME = "pf_handoff.json"


def assert_no_legacy_pf_handoff(release_root: Path) -> None:
    """``pf_handoff.json`` was replaced by HandoffManifest.v0 at ``handoff_to_pf.json``."""
    legacy = release_root.resolve() / LEGACY_PF_HANDOFF_NAME
    if legacy.is_file():
        raise ValueError(
            f"release must not contain legacy {LEGACY_PF_HANDOFF_NAME}; "
            f"use {HANDOFF_TO_PF_NAME} (HandoffManifest.v0)"
        )


def assert_release_phase2_protocol_artifacts(release_root: Path) -> list[str]:
    """
    Require Phase 2 protocol files and validate against pcs-core schemas.

    Returns check labels for CI logging.
    """
    import json

    release_root = release_root.resolve()
    assert_no_legacy_pf_handoff(release_root)

    checks: list[str] = ["no_legacy_pf_handoff"]
    for name in (HANDOFF_TO_PF_NAME, LABTRUST_RELEASE_FRAGMENT_NAME):
        path = release_root / name
        if not path.is_file():
            raise FileNotFoundError(f"missing Phase 2 protocol artifact: {name}")

    handoff = json.loads((release_root / HANDOFF_TO_PF_NAME).read_text(encoding="utf-8"))
    assert_handoff_manifest_valid(handoff)
    checks.append("handoff_manifest_schema")

    fragment = json.loads(
        (release_root / LABTRUST_RELEASE_FRAGMENT_NAME).read_text(encoding="utf-8")
    )
    assert_release_fragment_valid(fragment)
    assert_release_fragment_source_commit_matches_artifacts(release_root, fragment)
    checks.append("labtrust_release_fragment_schema")
    return checks
