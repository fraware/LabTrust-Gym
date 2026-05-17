"""LabTrust ReleaseManifest fragment (Phase 2 PR 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pcs_core")

from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_PF_NAME
from labtrust_gym.pcs.release_fragment import (
    LABTRUST_FRAGMENT_ARTIFACTS,
    LABTRUST_RELEASE_FRAGMENT_NAME,
    assert_release_fragment_source_commit_matches_artifacts,
    assert_release_fragment_valid,
    build_labtrust_release_fragment,
    emit_labtrust_release_fragment,
    release_fragment_schema_paths,
    validate_release_fragment,
)
from labtrust_gym.pcs.release_run import file_content_digest


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_release_fragment_lists_all_labtrust_artifacts(release_dir: Path) -> None:
    fragment_path = release_dir / LABTRUST_RELEASE_FRAGMENT_NAME
    if not fragment_path.is_file():
        doc = build_labtrust_release_fragment(release_dir)
    else:
        doc = _load(fragment_path)
    names = {name for name, _ in LABTRUST_FRAGMENT_ARTIFACTS}
    assert set(doc["artifacts"].keys()) == names


def test_release_fragment_hashes_match_files(release_dir: Path) -> None:
    fragment = build_labtrust_release_fragment(
        release_dir,
        source_commit=_load(release_dir / "manifest.json")["labtrust_gym_commit"],
    )
    for filename, _ in LABTRUST_FRAGMENT_ARTIFACTS:
        expected = file_content_digest(release_dir / filename)
        assert fragment["artifacts"][filename]["sha256"] == expected


def test_release_fragment_source_commit_matches_artifacts(release_dir: Path) -> None:
    fragment = build_labtrust_release_fragment(
        release_dir,
        source_commit=_load(release_dir / "manifest.json")["labtrust_gym_commit"],
    )
    assert_release_fragment_source_commit_matches_artifacts(release_dir, fragment)


def test_release_fragment_validates_against_pcs_core_if_schema_exists(release_dir: Path) -> None:
    if not release_fragment_schema_paths():
        pytest.skip("LabTrustReleaseFragment schema not available")
    fragment = build_labtrust_release_fragment(
        release_dir,
        source_commit=_load(release_dir / "manifest.json")["labtrust_gym_commit"],
    )
    assert_release_fragment_valid(fragment)
    assert validate_release_fragment(fragment) == []


def test_emit_release_fragment_writes_file(release_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / LABTRUST_RELEASE_FRAGMENT_NAME
    emit_labtrust_release_fragment(
        release_dir=release_dir,
        out_path=out,
        source_commit=_load(release_dir / "manifest.json")["labtrust_gym_commit"],
    )
    assert out.is_file()
    doc = _load(out)
    assert doc["artifacts"][HANDOFF_TO_PF_NAME]["artifact_type"] == "HandoffManifest.v0"
