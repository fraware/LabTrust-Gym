"""HandoffManifest.v0 emission and release-mode guards."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

pytest.importorskip("pcs_core")

from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_PF_NAME,
    assert_handoff_manifest_valid,
    assert_release_mode_handoff_provenance,
    build_bundle_to_verifier_handoff,
    emit_handoff_manifest,
)
from labtrust_gym.pcs.provenance import LOCAL_DEV_COMMIT
from labtrust_gym.pcs.release_protocol import (
    LEGACY_PF_HANDOFF_NAME,
    assert_no_legacy_pf_handoff,
    assert_release_phase2_protocol_artifacts,
)
from labtrust_gym.pcs.release_handoff import (
    assert_handoff_to_pf_bundle_hash_matches_certified_bundle,
    assert_handoff_to_pf_certificate_id_matches_trace_certificate,
    assert_handoff_to_pf_trace_hash_matches_runtime_receipt,
    assert_pf_handoff_matches_release_manifest,
)
from labtrust_gym.pcs.release_run import file_content_digest


def _load(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def test_emit_handoff_manifest_validates_against_pcs_core(release_dir: Path, tmp_path: Path) -> None:
    bundle = release_dir / "science_claim_bundle.certified.json"
    out = tmp_path / HANDOFF_TO_PF_NAME
    doc = emit_handoff_manifest(
        kind="bundle-to-verifier",
        bundle_path=bundle,
        out_path=out,
        release_mode=True,
    )
    assert_handoff_manifest_valid(doc)
    assert doc["handoff_kind"] == "bundle_to_verifier"
    assert out.is_file()


def test_handoff_manifest_certificate_id_matches_certified_bundle(release_dir: Path) -> None:
    assert_handoff_to_pf_certificate_id_matches_trace_certificate(release_dir)


def test_handoff_manifest_trace_hash_matches_runtime_receipt(release_dir: Path) -> None:
    assert_handoff_to_pf_trace_hash_matches_runtime_receipt(release_dir)


def test_handoff_manifest_bundle_hash_matches_certified_bundle(release_dir: Path) -> None:
    assert_handoff_to_pf_bundle_hash_matches_certified_bundle(release_dir)


def test_handoff_manifest_rejects_local_dev_in_release_mode(release_dir: Path) -> None:
    bundle = release_dir / "science_claim_bundle.certified.json"
    with pytest.raises(ValueError, match="local-dev"):
        build_bundle_to_verifier_handoff(
            bundle,
            release_mode=True,
            source_commit=LOCAL_DEV_COMMIT,
        )

    with pytest.raises(ValueError, match="local-dev"):
        assert_release_mode_handoff_provenance({"source_commit": LOCAL_DEV_COMMIT})


def test_emit_handoff_matches_release_manifest_after_write(release_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / HANDOFF_TO_PF_NAME
    emit_handoff_manifest(
        kind="bundle-to-verifier",
        bundle_path=release_dir / "science_claim_bundle.certified.json",
        out_path=out,
        release_mode=True,
    )
    manifest = _load(release_dir, "manifest.json")
    handoff = _load(tmp_path, HANDOFF_TO_PF_NAME)
    assert handoff["invariants"]["certificate_id"] == manifest["certificate_id"]
    assert handoff["invariants"]["trace_hash"] == manifest["trace_hash"]
    assert handoff["invariants"]["certified_bundle_hash"] == manifest["certified_bundle_hash"]


def test_release_phase2_protocol_gate(release_dir: Path) -> None:
    checks = assert_release_phase2_protocol_artifacts(release_dir)
    assert "handoff_manifest_schema" in checks
    assert "labtrust_release_fragment_schema" in checks


def test_release_rejects_legacy_pf_handoff_json(release_dir: Path, tmp_path: Path) -> None:
    drift = tmp_path / "release_legacy"
    import shutil

    shutil.copytree(release_dir, drift)
    (drift / LEGACY_PF_HANDOFF_NAME).write_text('{"legacy": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="pf_handoff"):
        assert_no_legacy_pf_handoff(drift)


def test_release_handoff_to_pf_committed_fixture(release_dir: Path) -> None:
    """Committed release/ includes HandoffManifest.v0 aligned with manifest.json."""
    path = release_dir / HANDOFF_TO_PF_NAME
    if not path.is_file():
        pytest.skip(f"{HANDOFF_TO_PF_NAME} not committed yet")
    assert_pf_handoff_matches_release_manifest(release_dir)
    on_disk = file_content_digest(release_dir / "science_claim_bundle.certified.json")
    handoff = _load(release_dir, HANDOFF_TO_PF_NAME)
    assert handoff["input_artifacts"]["science_claim_bundle.certified.json"]["sha256"] == on_disk
