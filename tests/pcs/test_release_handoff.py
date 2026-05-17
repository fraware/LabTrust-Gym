"""Atomic release handoff directory and PF certificate-id chain guards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_PF_NAME
from labtrust_gym.pcs.release_fixtures import release_fixture_present
from labtrust_gym.pcs.release_run import (
    RELEASE_HANDOFF_MANIFEST_NAME,
    build_handoff_for_pf,
    certificate_id_from_verification,
    validate_certificate_id_chain,
    validate_handoff_directory,
)


@pytest.fixture
def release_root(release_dir: Path) -> Path:
    if not release_fixture_present():
        pytest.fail("release/ fixtures missing; run generate_release_candidate.sh")
    return release_dir


def _load(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def test_release_handoff_directory_validates(release_root: Path) -> None:
    handoff = release_root / "handoff"
    assert handoff.is_dir(), "release/handoff/ required for PF signing"
    validate_handoff_directory(handoff)


def test_release_handoff_to_pf_matches_certified_bundle(release_root: Path) -> None:
    handoff = release_root / "handoff"
    certified = _load(handoff, "science_claim_bundle.certified.json")
    doc = _load(handoff, HANDOFF_TO_PF_NAME)
    expected = build_handoff_for_pf(handoff, source_commit=doc["source_commit"])
    inv = doc["invariants"]
    assert inv["certificate_id"] == expected["invariants"]["certificate_id"]
    assert inv["trace_hash"] == expected["invariants"]["trace_hash"]
    assert certified["certificates"][0]["certificate_id"] == inv["certificate_id"]


def test_release_handoff_manifest_certificate_id_matches_certified(release_root: Path) -> None:
    handoff = release_root / "handoff"
    manifest = _load(handoff, RELEASE_HANDOFF_MANIFEST_NAME)
    certified = _load(handoff, "science_claim_bundle.certified.json")
    assert manifest["certificate_id"] == certified["certificates"][0]["certificate_id"]
    assert manifest["trace_hash"] == certified["runtime_receipts"][0]["trace_hash"]


def test_release_signed_bundle_certificate_matches_certified(release_root: Path) -> None:
    signed_path = release_root / "signed_science_claim_bundle.json"
    if not signed_path.is_file():
        pytest.skip("signed_science_claim_bundle.json not committed (PF step optional in CI)")
    validate_certificate_id_chain(release_root)


def test_release_verification_certificate_id_matches_certified(release_root: Path) -> None:
    verification_path = release_root / "verification_result.json"
    if not verification_path.is_file():
        pytest.skip("verification_result.json not committed")
    certified = _load(release_root, "science_claim_bundle.certified.json")
    cert_id = certified["certificates"][0]["certificate_id"]
    verification = _load(release_root, "verification_result.json")
    assert certificate_id_from_verification(verification) == cert_id
