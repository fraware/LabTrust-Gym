"""verify_release_handoff promotion guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.release_fixtures import release_fixture_present
from labtrust_gym.pcs.release_handoff import (
    MANIFEST_NAME,
    PF_HANDOFF_NAME,
    build_canonical_release_manifest,
    build_pf_handoff,
    verify_release_handoff,
)


@pytest.fixture
def release_root(release_dir: Path) -> Path:
    if not release_fixture_present():
        pytest.fail("release/ fixtures missing")
    return release_dir


def test_verify_release_handoff_passes_on_committed_fixtures(release_root: Path) -> None:
    checks = verify_release_handoff(release_root)
    assert "certificate_id_propagation" in checks
    assert "pf_handoff" in checks


def test_verify_release_handoff_rejects_stale_cert_ref(release_root: Path, tmp_path: Path) -> None:
    import shutil

    shutil.copytree(release_root, tmp_path / "release", dirs_exist_ok=True)
    root = tmp_path / "release"
    certified = json.loads((root / "science_claim_bundle.certified.json").read_text(encoding="utf-8"))
    certified["claim_artifact"]["certificate_refs"] = ["cert-trace-stale-wrong-id"]
    (root / "science_claim_bundle.certified.json").write_text(json.dumps(certified), encoding="utf-8")
    with pytest.raises(ValueError, match="claim_artifact.certificate_refs"):
        verify_release_handoff(root)


def test_manifest_includes_artifact_hashes(release_root: Path) -> None:
    manifest = json.loads((release_root / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert "artifacts" in manifest
    assert len(manifest["artifacts"]) >= 5
    assert manifest.get("certified_bundle_hash", "").startswith("sha256:")
    pf = json.loads((release_root / PF_HANDOFF_NAME).read_text(encoding="utf-8"))
    assert pf["certified_bundle_hash"] == manifest["certified_bundle_hash"]
