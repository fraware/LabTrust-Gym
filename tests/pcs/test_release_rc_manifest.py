"""Release manifest, pf_handoff, and pcs-core RC sync gate tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from labtrust_gym.pcs.release_handoff import (
    MANIFEST_NAME,
    PF_HANDOFF_NAME,
    assert_pf_handoff_matches_release_manifest,
)
from labtrust_gym.pcs.release_run import file_content_digest
from labtrust_gym.pcs.sync_pcs_core_rc import (
    compare_release_to_pcs_core_rc,
    extract_rc_chain_identity,
    pcs_core_labtrust_release_dir,
)


@pytest.fixture
def pcs_core_canonical(repo_root: Path) -> Path:
    try:
        return pcs_core_labtrust_release_dir(repo_root)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))


def _load(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def test_release_manifest_matches_pcs_core_rc(release_dir: Path, pcs_core_canonical: Path) -> None:
    compare_release_to_pcs_core_rc(release_dir, pcs_core_canonical)
    manifest = _load(release_dir, MANIFEST_NAME)
    canonical = extract_rc_chain_identity(pcs_core_canonical)
    assert manifest["pcs_core_commit"] == canonical["pcs_core_commit"]
    assert manifest["certificate_id"] == canonical["certificate_id"]
    assert manifest["trace_hash"] == canonical["trace_hash"]
    assert manifest["certified_bundle_hash"] == canonical["certified_bundle_hash"]
    assert manifest["artifacts"]["trace.json"] == canonical["trace_json_hash"]
    assert manifest["artifacts"]["runtime_receipt.json"] == canonical["runtime_receipt_hash"]


def test_pf_handoff_matches_release_manifest(release_dir: Path) -> None:
    assert_pf_handoff_matches_release_manifest(release_dir)
    manifest = _load(release_dir, MANIFEST_NAME)
    pf = _load(release_dir, PF_HANDOFF_NAME)
    assert pf["certificate_id"] == manifest["certificate_id"]
    assert pf["certified_bundle_hash"] == manifest["certified_bundle_hash"]
    assert pf["trace_hash"] == manifest["trace_hash"]


def test_pf_handoff_matches_certified_bundle(release_dir: Path) -> None:
    pf = _load(release_dir, PF_HANDOFF_NAME)
    certified_path = release_dir / pf["certified_bundle"]
    assert pf["certified_bundle_hash"] == file_content_digest(certified_path)


def test_release_fixtures_reject_drift_from_pcs_core(
    release_dir: Path, pcs_core_canonical: Path, tmp_path: Path
) -> None:
    drift = tmp_path / "release_drift"
    shutil.copytree(release_dir, drift)
    manifest_path = drift / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pcs_core_commit"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="pcs_core_commit mismatch"):
        compare_release_to_pcs_core_rc(drift, pcs_core_canonical)
