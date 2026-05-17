"""Release manifest and pf_handoff alignment with pcs-core RC chain."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.release_handoff import MANIFEST_NAME, PF_HANDOFF_NAME
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
    local = _load(release_dir, MANIFEST_NAME)
    canonical = extract_rc_chain_identity(pcs_core_canonical)
    assert local["pcs_core_commit"] == canonical["pcs_core_commit"]
    assert local["certificate_id"] == canonical["certificate_id"]
    assert local["trace_hash"] == canonical["trace_hash"]
    assert local["certified_bundle_hash"] == canonical["certified_bundle_hash"]


def test_pf_handoff_matches_certified_bundle(release_dir: Path) -> None:
    pf = _load(release_dir, PF_HANDOFF_NAME)
    certified_path = release_dir / pf["certified_bundle"]
    assert pf["certified_bundle_hash"] == file_content_digest(certified_path)


def test_pf_handoff_certificate_id_matches_trace_certificate(release_dir: Path) -> None:
    pf = _load(release_dir, PF_HANDOFF_NAME)
    cert = _load(release_dir, "trace_certificate.json")
    assert pf["certificate_id"] == cert["certificate_id"]


def test_pf_handoff_trace_hash_matches_runtime_receipt(release_dir: Path) -> None:
    pf = _load(release_dir, PF_HANDOFF_NAME)
    receipt = _load(release_dir, "runtime_receipt.json")
    assert pf["trace_hash"] == receipt["trace_hash"]


def test_release_manifest_pcs_core_commit_current(release_dir: Path, pcs_core_canonical: Path) -> None:
    manifest = _load(release_dir, MANIFEST_NAME)
    fixture = _load(pcs_core_canonical, "RELEASE_FIXTURE_MANIFEST.json")
    expected = fixture["pcs_core_commit"]
    assert manifest["pcs_core_commit"] == expected
    assert len(manifest["pcs_core_commit"]) >= 40
