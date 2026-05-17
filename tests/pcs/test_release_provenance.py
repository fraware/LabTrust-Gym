"""Release fixture provenance: manifest SHAs must match artifact source_commit fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.manifest import PLACEHOLDER_COMMITS, validate_release_manifest
from labtrust_gym.pcs.release_fixtures import MANIFEST_NAME, release_fixture_present
from labtrust_gym.pcs.release_provenance import (
    labtrust_source_commit_paths,
    validate_release_artifact_provenance,
)


@pytest.fixture
def release_artifacts(release_dir: Path) -> Path:
    if not release_fixture_present():
        pytest.fail(
            "release/ fixtures missing on main; run generate_release_candidate.sh with CertifyEdge"
        )
    return release_dir


def _load(release_artifacts: Path, name: str) -> dict:
    return json.loads((release_artifacts / name).read_text(encoding="utf-8"))


def test_release_manifest_records_real_labtrust_commit(release_artifacts: Path) -> None:
    manifest = _load(release_artifacts, MANIFEST_NAME)
    receipt = _load(release_artifacts, "runtime_receipt.json")
    validate_release_manifest(manifest)
    assert manifest["labtrust_gym_commit"] not in PLACEHOLDER_COMMITS
    assert manifest["labtrust_gym_commit"] == receipt["source_commit"]


def test_release_manifest_records_real_certifyedge_commit(release_artifacts: Path) -> None:
    manifest = _load(release_artifacts, MANIFEST_NAME)
    cert = _load(release_artifacts, "trace_certificate.json")
    validate_release_manifest(manifest)
    assert manifest["certifyedge_commit"] not in PLACEHOLDER_COMMITS
    assert manifest["certifyedge_commit"] == cert["source_commit"]


def test_release_trace_certificate_commit_matches_certifyedge_commit(release_artifacts: Path) -> None:
    manifest = _load(release_artifacts, MANIFEST_NAME)
    cert = _load(release_artifacts, "trace_certificate.json")
    assert cert["source_commit"] == manifest["certifyedge_commit"]
    assert cert["source_commit"] != manifest["labtrust_gym_commit"]


def test_release_runtime_receipt_commit_matches_labtrust_commit(release_artifacts: Path) -> None:
    manifest = _load(release_artifacts, MANIFEST_NAME)
    receipt = _load(release_artifacts, "runtime_receipt.json")
    assert receipt["source_commit"] == manifest["labtrust_gym_commit"]


def test_release_bundle_nested_labtrust_artifacts_match_labtrust_commit(release_artifacts: Path) -> None:
    manifest = _load(release_artifacts, MANIFEST_NAME)
    lt = manifest["labtrust_gym_commit"]
    for bundle_name in ("science_claim_bundle.pending.json", "science_claim_bundle.certified.json"):
        bundle = _load(release_artifacts, bundle_name)
        for path, commit in labtrust_source_commit_paths(bundle):
            assert commit == lt, f"{bundle_name} {path} source_commit mismatch"


def test_release_fixture_contains_no_placeholder_commits(release_artifacts: Path) -> None:
    manifest = _load(release_artifacts, MANIFEST_NAME)
    validate_release_artifact_provenance(release_artifacts, manifest)
    for key in ("labtrust_gym_commit", "certifyedge_commit", "pcs_core_commit"):
        assert manifest[key] not in PLACEHOLDER_COMMITS
    for name in (
        "runtime_receipt.json",
        "trace_certificate.json",
        "science_claim_bundle.pending.json",
        "science_claim_bundle.certified.json",
    ):
        doc = _load(release_artifacts, name)
        if "source_commit" in doc:
            assert doc["source_commit"] not in PLACEHOLDER_COMMITS
