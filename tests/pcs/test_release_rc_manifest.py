"""Release manifest, pf_handoff, and pcs-core RC sync gate tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from labtrust_gym.pcs.release_handoff import (
    MANIFEST_NAME,
    PF_HANDOFF_NAME,
    assert_pf_handoff_certificate_id_matches_trace_certificate,
    assert_pf_handoff_matches_release_manifest,
    assert_pf_handoff_trace_hash_matches_runtime_receipt,
)
from labtrust_gym.pcs.release_run import file_content_digest
from labtrust_gym.pcs.schema_version import (
    CANONICAL_BUNDLE_ARRAY_KEYS,
    LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS,
    assert_no_legacy_pf_bundle_keys,
)
from labtrust_gym.pcs.sync_pcs_core_rc import (
    HANDOFF_ARTIFACTS,
    assert_release_not_using_deterministic_cert_digest,
    assert_release_not_using_local_dev,
    assert_release_not_using_mock_certificate,
    assert_release_not_using_mock_or_placeholder,
    assert_release_not_using_placeholder_commits,
    compare_release_to_pcs_core_rc,
    extract_rc_chain_identity,
    pcs_core_labtrust_release_dir,
    sync_release_from_pcs_core_rc,
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
    assert pf["certified_bundle"] == "science_claim_bundle.certified.json"
    assert pf["certificate_id"] == manifest["certificate_id"]
    assert pf["certified_bundle_hash"] == manifest["certified_bundle_hash"]
    assert pf["trace_hash"] == manifest["trace_hash"]


def test_pf_handoff_matches_certified_bundle(release_dir: Path) -> None:
    pf = _load(release_dir, PF_HANDOFF_NAME)
    certified_path = release_dir / pf["certified_bundle"]
    assert pf["certified_bundle_hash"] == file_content_digest(certified_path)


def test_pf_handoff_certificate_id_matches_trace_certificate(release_dir: Path) -> None:
    assert_pf_handoff_certificate_id_matches_trace_certificate(release_dir)


def test_pf_handoff_trace_hash_matches_runtime_receipt(release_dir: Path) -> None:
    assert_pf_handoff_trace_hash_matches_runtime_receipt(release_dir)


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


def test_release_fixtures_do_not_use_mock_certificate(release_dir: Path) -> None:
    assert_release_not_using_mock_certificate(release_dir)


def test_release_fixtures_do_not_use_deterministic_cert_digest(release_dir: Path) -> None:
    assert_release_not_using_deterministic_cert_digest(release_dir)


def test_release_fixtures_do_not_use_local_dev(release_dir: Path) -> None:
    assert_release_not_using_local_dev(release_dir)


def test_release_fixtures_do_not_use_placeholder_commits(release_dir: Path) -> None:
    assert_release_not_using_placeholder_commits(release_dir)


def test_release_fixtures_mock_guard_umbrella(release_dir: Path) -> None:
    assert_release_not_using_mock_or_placeholder(release_dir)


def test_sync_from_pcs_core_rc_is_idempotent(
    repo_root: Path, pcs_core_canonical: Path, tmp_path: Path
) -> None:
    """Two syncs from the same canonical tree produce identical handoff artifact bytes."""
    work = tmp_path / "lt_work"
    shutil.copytree(repo_root, work, ignore=shutil.ignore_patterns(".git", ".venv*", "tmp_*"))
    release_rel = Path("examples/pcs_qc_release/release")
    backup = tmp_path / "release_backup"
    if (work / release_rel).is_dir():
        shutil.copytree(work / release_rel, backup)

    try:
        first = sync_release_from_pcs_core_rc(labtrust_root=work, canonical=pcs_core_canonical)
        digests_first = {name: file_content_digest(first / name) for name in HANDOFF_ARTIFACTS}
        second = sync_release_from_pcs_core_rc(labtrust_root=work, canonical=pcs_core_canonical)
        digests_second = {name: file_content_digest(second / name) for name in HANDOFF_ARTIFACTS}
        assert digests_first == digests_second
    finally:
        if backup.is_dir():
            dest = work / release_rel
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(backup, dest)


@pytest.mark.parametrize("bundle_name", ("science_claim_bundle.pending.json", "science_claim_bundle.certified.json"))
def test_release_bundle_uses_runtime_receipts_array(release_dir: Path, bundle_name: str) -> None:
    bundle = _load(release_dir, bundle_name)
    assert isinstance(bundle["runtime_receipts"], list)
    assert len(bundle["runtime_receipts"]) >= 1


@pytest.mark.parametrize("bundle_name", ("science_claim_bundle.pending.json", "science_claim_bundle.certified.json"))
def test_release_bundle_uses_certificates_array(release_dir: Path, bundle_name: str) -> None:
    bundle = _load(release_dir, bundle_name)
    assert isinstance(bundle["certificates"], list)
    if bundle_name.endswith("certified.json"):
        assert len(bundle["certificates"]) >= 1


def test_release_bundle_does_not_use_legacy_singular_fields(release_dir: Path) -> None:
    for bundle_name in ("science_claim_bundle.pending.json", "science_claim_bundle.certified.json"):
        bundle = _load(release_dir, bundle_name)
        assert_no_legacy_pf_bundle_keys(bundle)
        for key in LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS:
            assert key not in bundle
        assert CANONICAL_BUNDLE_ARRAY_KEYS.issubset(bundle.keys())
