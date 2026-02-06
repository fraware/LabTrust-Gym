"""
Assert that the coordination policy fingerprint is stable: same policy files
yield the same fingerprint; changing content or set yields a different fingerprint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_card import (
    COORDINATION_POLICY_FILES,
    coordination_policy_fingerprint,
    copy_frozen_coordination_policy,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_card_fingerprint_stable_same_policy() -> None:
    """Same policy directory yields the same fingerprint on repeated calls."""
    repo = _repo_root()
    if not (repo / "policy" / "coordination").is_dir():
        pytest.skip("policy/coordination not found")
    fp1 = coordination_policy_fingerprint(repo)
    fp2 = coordination_policy_fingerprint(repo)
    assert fp1 == fp2
    assert len(fp1) == 64
    assert all(c in "0123456789abcdef" for c in fp1)


def test_card_fingerprint_different_content_different_fingerprint(
    tmp_path: Path,
) -> None:
    """Changing a policy file content yields a different fingerprint."""
    repo = _repo_root()
    coord_dir = repo / "policy" / "coordination"
    if not coord_dir.is_dir():
        pytest.skip("policy/coordination not found")
    # Build a mirror with one file content changed
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "policy" / "coordination").mkdir(parents=True)
    for name in COORDINATION_POLICY_FILES:
        src = coord_dir / name
        if src.is_file():
            (mirror / "policy" / "coordination" / name).write_bytes(src.read_bytes())
    fp_original = coordination_policy_fingerprint(mirror)
    # Tamper one file
    first_file = COORDINATION_POLICY_FILES[0]
    path = mirror / "policy" / "coordination" / first_file
    if path.is_file():
        path.write_text(path.read_text() + "\n# comment\n")
    fp_tampered = coordination_policy_fingerprint(mirror)
    assert fp_original != fp_tampered


def test_frozen_copy_manifest_contains_fingerprint(tmp_path: Path) -> None:
    """copy_frozen_coordination_policy writes manifest.json with coordination_policy_fingerprint."""
    import json

    repo = _repo_root()
    if not (repo / "policy" / "coordination").is_dir():
        pytest.skip("policy/coordination not found")
    fp = copy_frozen_coordination_policy(repo, tmp_path / "frozen")
    manifest_path = tmp_path / "frozen" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("coordination_policy_fingerprint") == fp
    assert "files" in manifest
    assert len(manifest["files"]) >= 1
    for entry in manifest["files"]:
        assert "path" in entry and "sha256" in entry
        assert len(entry["sha256"]) == 64
