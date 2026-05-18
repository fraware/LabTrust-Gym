"""Phase 2 PCS protocol artifact guards for LabTrust ``release/``."""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    assert_handoff_manifest_valid,
    assert_handoff_registry_check,
)
from labtrust_gym.pcs.release_fragment import (
    LABTRUST_RELEASE_FRAGMENT_NAME,
    assert_release_fragment_source_commit_matches_artifacts,
    assert_release_fragment_valid,
)

LEGACY_PF_HANDOFF_NAME = "pf_handoff.json"
LEGACY_HANDOFF_SUBDIR_GUARD = "handoff_for_pf.json"


def assert_no_legacy_handoff_subdir_guard(handoff_root: Path) -> None:
    """``release/handoff/`` must use HandoffManifest.v0, not legacy guard JSON."""
    legacy = handoff_root.resolve() / LEGACY_HANDOFF_SUBDIR_GUARD
    if legacy.is_file():
        raise ValueError(
            f"handoff/ must not contain legacy {LEGACY_HANDOFF_SUBDIR_GUARD}; "
            f"use {HANDOFF_TO_PF_NAME}"
        )


def assert_no_legacy_pf_handoff(release_root: Path) -> None:
    """``pf_handoff.json`` was replaced by HandoffManifest.v0 at ``handoff_to_pf.json``."""
    legacy = release_root.resolve() / LEGACY_PF_HANDOFF_NAME
    if legacy.is_file():
        raise ValueError(
            f"release must not contain legacy {LEGACY_PF_HANDOFF_NAME}; "
            f"use {HANDOFF_TO_PF_NAME} (HandoffManifest.v0)"
        )


def assert_release_mode_handoff_layout(release_root: Path) -> list[str]:
    """
    Release mode: forbid legacy handoff files and require Phase 2 handoffs at release root.

    Also validates ``handoff/`` subdirectory when present.
    """
    release_root = release_root.resolve()
    checks: list[str] = []

    assert_no_legacy_pf_handoff(release_root)
    checks.append("no_legacy_pf_handoff_root")

    for name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME):
        if not (release_root / name).is_file():
            raise FileNotFoundError(f"release mode missing required handoff: {name}")

    handoff_sub = release_root / "handoff"
    if handoff_sub.is_dir():
        assert_no_legacy_handoff_subdir_guard(handoff_sub)
        checks.append("no_legacy_handoff_for_pf_in_handoff_subdir")
        legacy_pf = handoff_sub / LEGACY_PF_HANDOFF_NAME
        if legacy_pf.is_file():
            raise ValueError(f"handoff/ must not contain legacy {LEGACY_PF_HANDOFF_NAME}")
    checks.append("required_handoffs_present")
    return checks


def assert_release_phase2_protocol_artifacts(release_root: Path) -> list[str]:
    """
    Require Phase 2 protocol files and validate against pcs-core schemas.

    Returns check labels for CI logging.
    """
    import json

    release_root = release_root.resolve()
    checks = assert_release_mode_handoff_layout(release_root)
    for name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME, LABTRUST_RELEASE_FRAGMENT_NAME):
        path = release_root / name
        if not path.is_file():
            raise FileNotFoundError(f"missing Phase 2 protocol artifact: {name}")

    for name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME):
        path = release_root / name
        handoff = json.loads(path.read_text(encoding="utf-8"))
        assert_handoff_manifest_valid(handoff)
        assert_handoff_registry_check(path)
    checks.append("handoff_manifest_schema")
    checks.append("handoff_registry_check")

    fragment = json.loads(
        (release_root / LABTRUST_RELEASE_FRAGMENT_NAME).read_text(encoding="utf-8")
    )
    assert_release_fragment_valid(fragment)
    assert_release_fragment_source_commit_matches_artifacts(release_root, fragment)
    checks.append("labtrust_release_fragment_schema")
    return checks


def assert_handoff_digests_not_stale(release_root: Path) -> list[str]:
    """Fail when handoff input artifact hashes or fragment entries disagree with on-disk bytes."""
    import json

    from labtrust_gym.pcs.release_fragment import LABTRUST_RELEASE_FRAGMENT_NAME
    from labtrust_gym.pcs.release_run import file_content_digest

    release_root = release_root.resolve()
    checks: list[str] = []

    for handoff_name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME):
        path = release_root / handoff_name
        handoff = json.loads(path.read_text(encoding="utf-8"))
        for artifact_name, ref in (handoff.get("input_artifacts") or {}).items():
            artifact_path = release_root / artifact_name
            if not artifact_path.is_file():
                raise FileNotFoundError(f"{handoff_name} references missing input {artifact_name}")
            on_disk = file_content_digest(artifact_path)
            expected = ref.get("sha256")
            if expected != on_disk:
                raise ValueError(
                    f"stale handoff digest for {handoff_name} input {artifact_name}: "
                    f"handoff={expected!r} on_disk={on_disk!r}"
                )
        checks.append(f"{handoff_name}_input_digests_fresh")

    fragment_path = release_root / LABTRUST_RELEASE_FRAGMENT_NAME
    if fragment_path.is_file():
        fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
        for artifact_name, ref in (fragment.get("artifacts") or {}).items():
            artifact_path = release_root / artifact_name
            if not artifact_path.is_file():
                raise FileNotFoundError(f"fragment references missing artifact {artifact_name}")
            on_disk = file_content_digest(artifact_path)
            if ref.get("sha256") != on_disk:
                raise ValueError(
                    f"stale fragment digest for {artifact_name}: "
                    f"fragment={ref.get('sha256')!r} on_disk={on_disk!r}"
                )
        checks.append("fragment_artifact_digests_fresh")

    return checks
