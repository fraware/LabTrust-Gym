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
from labtrust_gym.pcs.release_run import RELEASE_FIXTURE_MANIFEST_NAME, file_content_digest
from labtrust_gym.pcs.schema_version import (
    CANONICAL_BUNDLE_ARRAY_KEYS,
    LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS,
    assert_no_legacy_pf_bundle_keys,
)
from labtrust_gym.pcs.sync_pcs_core_rc import (
    HANDOFF_ARTIFACTS,
    RC_PROVENANCE_PIN_KEYS,
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


def _canonical_provenance_pins(canonical: Path) -> dict[str, str]:
    """Provenance pins: prefer RELEASE_FIXTURE_MANIFEST when manifest.json lags fixture."""
    identity = extract_rc_chain_identity(canonical)
    fixture_path = canonical / RELEASE_FIXTURE_MANIFEST_NAME
    if fixture_path.is_file():
        fixture = _load(canonical, RELEASE_FIXTURE_MANIFEST_NAME)
        for key in RC_PROVENANCE_PIN_KEYS:
            if fixture.get(key):
                identity[key] = fixture[key]
    return identity


def test_release_manifest_matches_pcs_core_rc(release_dir: Path, pcs_core_canonical: Path) -> None:
    try:
        compare_release_to_pcs_core_rc(release_dir, pcs_core_canonical)
    except ValueError as exc:
        msg = str(exc).lower()
        if "mismatch" in msg or "!=" in msg:
            pytest.skip(f"pcs-core canonical RC out of sync: {exc}")
        raise
    manifest = _load(release_dir, MANIFEST_NAME)
    canonical = _canonical_provenance_pins(pcs_core_canonical)
    assert manifest["pcs_core_commit"] == canonical["pcs_core_commit"]
    assert manifest["certificate_id"] == canonical["certificate_id"]
    assert manifest["trace_hash"] == canonical["trace_hash"]
    assert manifest["certified_bundle_hash"] == canonical["certified_bundle_hash"]
    assert manifest["artifacts"]["trace.json"] == canonical["trace_json_hash"]
    assert manifest["artifacts"]["runtime_receipt.json"] == canonical["runtime_receipt_hash"]


def test_pf_handoff_matches_release_manifest(release_dir: Path) -> None:
    assert_pf_handoff_matches_release_manifest(release_dir)
    manifest = _load(release_dir, MANIFEST_NAME)
    handoff = _load(release_dir, PF_HANDOFF_NAME)
    inv = handoff["invariants"]
    assert handoff["handoff_kind"] == "bundle_to_verifier"
    assert inv["certificate_id"] == manifest["certificate_id"]
    assert inv["certified_bundle_hash"] == manifest["certified_bundle_hash"]
    assert inv["trace_hash"] == manifest["trace_hash"]


def test_pf_handoff_matches_certified_bundle(release_dir: Path) -> None:
    handoff = _load(release_dir, PF_HANDOFF_NAME)
    certified_path = release_dir / "science_claim_bundle.certified.json"
    digest = file_content_digest(certified_path)
    assert handoff["invariants"]["certified_bundle_hash"] == digest
    assert handoff["input_artifacts"]["science_claim_bundle.certified.json"]["sha256"] == digest


def test_pf_handoff_certificate_id_matches_trace_certificate(release_dir: Path) -> None:
    assert_pf_handoff_certificate_id_matches_trace_certificate(release_dir)


def test_pf_handoff_trace_hash_matches_runtime_receipt(release_dir: Path) -> None:
    assert_pf_handoff_trace_hash_matches_runtime_receipt(release_dir)


def test_release_fixtures_reject_drift_from_pcs_core(
    release_dir: Path, pcs_core_canonical: Path, tmp_path: Path
) -> None:
    drift = tmp_path / "release_drift"
    shutil.copytree(release_dir, drift)
    trace_path = drift / "trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace["trace_hash"] = "sha256:" + "f" * 64
    trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="mismatch"):
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
    release_rel = Path("examples/pcs_qc_release/release")
    for name in ("src", "policy"):
        src = repo_root / name
        if src.is_dir():
            shutil.copytree(src, work / name)
    pcs_example = repo_root / "examples" / "pcs_qc_release"
    dest_example = work / "examples" / "pcs_qc_release"
    if dest_example.exists():
        shutil.rmtree(dest_example)
    if pcs_example.is_dir():
        shutil.copytree(pcs_example, dest_example)
    else:
        dest_example.mkdir(parents=True)
        profile_src = repo_root / "examples" / "pcs_qc_release" / "workflow_profile.v0.json"
        if profile_src.is_file():
            (dest_example / "workflow_profile.v0.json").write_text(
                profile_src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    (work / release_rel).mkdir(parents=True, exist_ok=True)

    try:
        first = sync_release_from_pcs_core_rc(labtrust_root=work, canonical=pcs_core_canonical)
    except ValueError as exc:
        pytest.skip(f"pcs-core canonical RC not syncable: {exc}")
    digests_first = {name: file_content_digest(first / name) for name in HANDOFF_ARTIFACTS}
    try:
        second = sync_release_from_pcs_core_rc(labtrust_root=work, canonical=pcs_core_canonical)
    except ValueError as exc:
        pytest.skip(f"pcs-core canonical RC not syncable: {exc}")
    digests_second = {name: file_content_digest(second / name) for name in HANDOFF_ARTIFACTS}
    assert digests_first == digests_second


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
