"""Cross-repo release/ fixtures (real CertifyEdge certificate; required when release/ is committed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.deterministic import DETERMINISTIC_CERT_DIGEST, DETERMINISTIC_CERTIFICATE_ID
from labtrust_gym.pcs.manifest import PLACEHOLDER_COMMITS, validate_release_manifest
from labtrust_gym.pcs.mock_certificate import CERTIFYEDGE_SOURCE_REPO, is_mock_certificate
from labtrust_gym.pcs.release_fixtures import (
    MANIFEST_NAME,
    release_fixture_present,
    validate_release_fixtures,
)
from labtrust_gym.pcs.validate import require_pcs_core, validate_science_claim_bundle

pcs_core = pytest.importorskip("pcs_core")

pytestmark = pytest.mark.skipif(
    not release_fixture_present(),
    reason="release/ fixtures not committed; run generate_release_candidate.sh with CertifyEdge",
)


@pytest.fixture
def release_artifacts(release_dir: Path) -> Path:
    if not release_fixture_present():
        pytest.skip("release/ not populated")
    return release_dir


def _load(release_artifacts: Path, name: str) -> dict:
    return json.loads((release_artifacts / name).read_text(encoding="utf-8"))


def test_mock_certificate_not_used_for_release_fixture(release_artifacts: Path) -> None:
    cert = _load(release_artifacts, "trace_certificate.json")
    assert not is_mock_certificate(cert)
    assert cert.get("signature_or_digest") != DETERMINISTIC_CERT_DIGEST


def test_release_fixture_uses_real_certifyedge_certificate(release_artifacts: Path) -> None:
    cert = _load(release_artifacts, "trace_certificate.json")
    assert cert.get("source_repo") == CERTIFYEDGE_SOURCE_REPO
    assert str(cert.get("producer", "")).lower() == "certifyedge"
    assert cert.get("signature_or_digest") != DETERMINISTIC_CERT_DIGEST
    assert cert.get("certificate_id") != DETERMINISTIC_CERTIFICATE_ID

    manifest = _load(release_artifacts, MANIFEST_NAME)
    assert manifest.get("mock_certificate") is False
    validate_release_manifest(manifest)
    for key in ("labtrust_gym_commit", "certifyedge_commit", "pcs_core_commit"):
        assert manifest[key] not in PLACEHOLDER_COMMITS


def test_release_certified_bundle_validates_against_pcs_core(release_artifacts: Path) -> None:
    require_pcs_core()
    certified = _load(release_artifacts, "science_claim_bundle.certified.json")
    validate_science_claim_bundle(certified)
    pcs_core.validate.validate_artifact(certified)
    pcs_core.validate.validate_file(release_artifacts / "science_claim_bundle.certified.json")


def test_release_certified_bundle_certificate_source_repo_is_certifyedge(release_artifacts: Path) -> None:
    certified = _load(release_artifacts, "science_claim_bundle.certified.json")
    assert certified["certificates"]
    assert certified["certificates"][0]["source_repo"] == CERTIFYEDGE_SOURCE_REPO


def test_release_certified_bundle_trace_hash_matches_receipt(release_artifacts: Path) -> None:
    receipt = _load(release_artifacts, "runtime_receipt.json")
    trace = _load(release_artifacts, "trace.json")
    certified = _load(release_artifacts, "science_claim_bundle.certified.json")
    th = receipt["trace_hash"]
    assert trace["trace_hash"] == th
    assert certified["runtime_receipts"][0]["trace_hash"] == th
    assert certified["certificates"][0]["trace_hash"] == th


def test_release_fixtures_validate_helper(release_artifacts: Path) -> None:
    names = validate_release_fixtures(release_artifacts)
    assert "science_claim_bundle.certified.json" in names
    assert MANIFEST_NAME in names
