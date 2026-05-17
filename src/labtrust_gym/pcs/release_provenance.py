"""Provenance consistency checks for committed ``release/`` fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from labtrust_gym.pcs.manifest import PLACEHOLDER_COMMITS, validate_release_manifest
from labtrust_gym.pcs.mock_certificate import CERTIFYEDGE_SOURCE_REPO


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def labtrust_source_commit_paths(bundle: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """Yield (path, source_commit) for LabTrust-nested PCS artifacts in a bundle."""
    yield "bundle", bundle["source_commit"]
    for key in ("assumption_set", "claim_artifact", "evidence_bundle"):
        nested = bundle.get(key)
        if isinstance(nested, dict) and "source_commit" in nested:
            yield key, nested["source_commit"]
    for i, receipt in enumerate(bundle.get("runtime_receipts", [])):
        yield f"runtime_receipts[{i}]", receipt["source_commit"]


def assert_no_placeholder_commits(commit: str, *, context: str) -> None:
    if not commit or commit in PLACEHOLDER_COMMITS:
        raise ValueError(f"{context}: placeholder or missing source_commit {commit!r}")


def validate_release_artifact_provenance(release_root: Path, manifest: dict[str, Any]) -> None:
    """Ensure every artifact source_commit matches manifest repo SHAs."""
    validate_release_manifest(manifest)
    lt = manifest["labtrust_gym_commit"]
    ce = manifest["certifyedge_commit"]

    receipt = _load(release_root / "runtime_receipt.json")
    assert_no_placeholder_commits(receipt["source_commit"], context="runtime_receipt")
    if receipt["source_commit"] != lt:
        raise ValueError("runtime_receipt.source_commit must equal manifest.labtrust_gym_commit")

    pending = _load(release_root / "science_claim_bundle.pending.json")
    for path, commit in labtrust_source_commit_paths(pending):
        assert_no_placeholder_commits(commit, context=f"pending.{path}")
        if commit != lt:
            raise ValueError(f"pending.{path} source_commit must equal manifest.labtrust_gym_commit")

    certificate = _load(release_root / "trace_certificate.json")
    assert_no_placeholder_commits(certificate["source_commit"], context="trace_certificate")
    if certificate["source_commit"] != ce:
        raise ValueError("trace_certificate.source_commit must equal manifest.certifyedge_commit")
    if certificate["source_commit"] == lt:
        raise ValueError("trace_certificate must not use LabTrust gym commit as source_commit")
    if certificate.get("source_repo") != CERTIFYEDGE_SOURCE_REPO:
        raise ValueError("trace_certificate.source_repo must be CertifyEdge")

    certified = _load(release_root / "science_claim_bundle.certified.json")
    for path, commit in labtrust_source_commit_paths(certified):
        assert_no_placeholder_commits(commit, context=f"certified.{path}")
        if commit != lt:
            raise ValueError(f"certified.{path} source_commit must equal manifest.labtrust_gym_commit")
    for i, cert in enumerate(certified.get("certificates", [])):
        assert_no_placeholder_commits(cert["source_commit"], context=f"certificates[{i}]")
        if cert["source_commit"] != ce:
            raise ValueError(f"certified.certificates[{i}].source_commit must equal manifest.certifyedge_commit")
        if cert["source_commit"] == lt:
            raise ValueError("embedded certificate must not use LabTrust commit")
