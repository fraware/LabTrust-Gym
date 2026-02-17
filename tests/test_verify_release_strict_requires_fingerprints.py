"""
verify-release --strict-fingerprints must fail when EvidenceBundle manifest
is missing a required fingerprint (e.g. memory_policy_fingerprint).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.export.verify import REQUIRED_STRICT_FINGERPRINTS, verify_bundle


def test_verify_bundle_strict_fails_when_memory_policy_fingerprint_missing(
    tmp_path: Path,
) -> None:
    """Minimal bundle manifest missing memory_policy_fingerprint -> strict verification fails."""
    bundle_dir = tmp_path / "EvidenceBundle.v0.1"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    # Manifest with three fingerprints present but memory_policy_fingerprint missing
    manifest: dict = {
        "version": "0.1",
        "files": [],
        "coordination_policy_fingerprint": "a" * 64,
        "rbac_policy_fingerprint": "b" * 64,
        "tool_registry_fingerprint": "c" * 64,
        # memory_policy_fingerprint omitted
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # policy_root: use repo so schema/rbac paths exist; mismatch may occur but strict fails first
    root = Path(__file__).resolve().parent.parent
    passed, _report, errors = verify_bundle(
        bundle_dir,
        policy_root=root,
        strict_fingerprints=True,
    )
    assert passed is False
    assert any(
        "memory_policy_fingerprint" in e or "strict-fingerprints requires" in e
        for e in errors
    ), f"expected error about missing memory_policy_fingerprint; got {errors}"


def test_verify_bundle_strict_fails_when_required_key_empty(tmp_path: Path) -> None:
    """Manifest with memory_policy_fingerprint present but empty -> strict fails."""
    bundle_dir = tmp_path / "EvidenceBundle.v0.1"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "0.1",
        "files": [],
        "coordination_policy_fingerprint": "a" * 64,
        "rbac_policy_fingerprint": "b" * 64,
        "tool_registry_fingerprint": "c" * 64,
        "memory_policy_fingerprint": "",  # empty
    }
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parent.parent
    passed, _report, errors = verify_bundle(
        bundle_dir,
        policy_root=root,
        strict_fingerprints=True,
    )
    assert passed is False
    assert any(
        "memory_policy_fingerprint" in e or "strict-fingerprints requires" in e
        for e in errors
    ), f"expected error about empty memory_policy_fingerprint; got {errors}"


def test_strict_required_keys_list_complete() -> None:
    """REQUIRED_STRICT_FINGERPRINTS includes all four provenance keys."""
    assert "memory_policy_fingerprint" in REQUIRED_STRICT_FINGERPRINTS
    assert "coordination_policy_fingerprint" in REQUIRED_STRICT_FINGERPRINTS
    assert "rbac_policy_fingerprint" in REQUIRED_STRICT_FINGERPRINTS
    assert "tool_registry_fingerprint" in REQUIRED_STRICT_FINGERPRINTS
    assert len(REQUIRED_STRICT_FINGERPRINTS) == 4
