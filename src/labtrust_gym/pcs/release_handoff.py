"""Canonical LabTrust release handoff manifest and promotion guards for pcs-core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.manifest import validate_release_manifest
from labtrust_gym.pcs.mock_certificate import CERTIFYEDGE_SOURCE_REPO
from labtrust_gym.pcs.release_provenance import (
    assert_no_placeholder_commits,
    labtrust_source_commit_paths,
    validate_release_artifact_provenance,
)
from labtrust_gym.pcs.release_run import (
    HANDOFF_ARTIFACTS,
    file_content_digest,
    certified_bundle_ids,
)

CERTIFIED_BUNDLE_NAME = "science_claim_bundle.certified.json"
MANIFEST_NAME = "manifest.json"
PF_HANDOFF_NAME = "pf_handoff.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_canonical_release_manifest(
    release_root: Path,
    handoff_manifest: dict[str, Any],
    *,
    generator: str,
    certifyedge_bin: str,
    certifyedge_spec: str,
) -> dict[str, Any]:
    """Write ``release/manifest.json`` with commits, trace/certificate ids, and artifact digests."""
    release_root = release_root.resolve()
    certified_path = release_root / CERTIFIED_BUNDLE_NAME
    certificate = _load(release_root / "trace_certificate.json")

    spec_recorded = certifyedge_spec
    if certifyedge_spec:
        spec_path = Path(certifyedge_spec)
        if spec_path.is_absolute():
            try:
                from labtrust_gym.config import get_repo_root

                spec_recorded = spec_path.relative_to(get_repo_root().parent).as_posix()
            except ValueError:
                spec_recorded = spec_path.as_posix()

    certified_bundle_hash = file_content_digest(certified_path)
    manifest: dict[str, Any] = {
        "schema_version": "v0",
        "handoff_id": handoff_manifest["handoff_id"],
        "generated_at": handoff_manifest.get("generated_at"),
        "generator": generator,
        "mock_certificate": False,
        "labtrust_gym_commit": handoff_manifest["labtrust_gym_commit"],
        "certifyedge_commit": handoff_manifest["certifyedge_commit"],
        "pcs_core_commit": handoff_manifest["pcs_core_commit"],
        "certifyedge_bin": certifyedge_bin,
        "certifyedge_spec": spec_recorded,
        "certificate_id": handoff_manifest["certificate_id"],
        "certificate_source_repo": certificate.get("source_repo"),
        "certificate_producer": certificate.get("producer"),
        "certified_bundle_id": handoff_manifest["certified_bundle_id"],
        "trace_hash": handoff_manifest["trace_hash"],
        "certified_bundle_hash": certified_bundle_hash,
        "artifacts": dict(handoff_manifest["artifacts"]),
    }
    path = release_root / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def build_pf_handoff(release_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Write ``release/pf_handoff.json`` for Provability Fabric bundle-hash guard."""
    doc = {
        "schema_version": "v0",
        "certified_bundle": CERTIFIED_BUNDLE_NAME,
        "certified_bundle_hash": manifest["certified_bundle_hash"],
        "certificate_id": manifest["certificate_id"],
        "trace_hash": manifest["trace_hash"],
    }
    path = release_root / PF_HANDOFF_NAME
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def _assert_certificate_id_propagation(release_root: Path, certificate_id: str) -> None:
    certificate = _load(release_root / "trace_certificate.json")
    certified = _load(release_root / CERTIFIED_BUNDLE_NAME)

    if certificate["certificate_id"] != certificate_id:
        raise ValueError("trace_certificate.certificate_id != manifest.certificate_id")
    if certified["certificates"][0]["certificate_id"] != certificate_id:
        raise ValueError("certified.certificates[0].certificate_id != manifest.certificate_id")
    claim_refs = certified["claim_artifact"].get("certificate_refs", [])
    if not claim_refs or claim_refs[0] != certificate_id:
        raise ValueError("claim_artifact.certificate_refs[0] != manifest.certificate_id")
    evidence_refs = certified["evidence_bundle"].get("certificate_refs", [])
    if not evidence_refs or evidence_refs[0] != certificate_id:
        raise ValueError("evidence_bundle.certificate_refs[0] != manifest.certificate_id")


def _assert_trace_hash_stable(release_root: Path, trace_hash: str) -> None:
    trace = _load(release_root / "trace.json")
    receipt = _load(release_root / "runtime_receipt.json")
    certificate = _load(release_root / "trace_certificate.json")
    certified = _load(release_root / CERTIFIED_BUNDLE_NAME)

    for label, doc in (
        ("trace.json", trace),
        ("runtime_receipt.json", receipt),
        ("trace_certificate.json", certificate),
    ):
        if doc.get("trace_hash") != trace_hash:
            raise ValueError(f"{label} trace_hash != manifest.trace_hash")

    if certified["runtime_receipts"][0]["trace_hash"] != trace_hash:
        raise ValueError("certified.runtime_receipts[0].trace_hash != manifest.trace_hash")
    if certified["certificates"][0]["trace_hash"] != trace_hash:
        raise ValueError("certified.certificates[0].trace_hash != manifest.trace_hash")


def _assert_manifest_artifact_digests(release_root: Path, manifest: dict[str, Any]) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("manifest.artifacts must be a non-empty object")
    for name in HANDOFF_ARTIFACTS:
        if name not in artifacts:
            raise ValueError(f"manifest.artifacts missing {name}")
    for name, expected in artifacts.items():
        path = release_root / name
        if not path.is_file():
            raise FileNotFoundError(f"manifest artifact missing on disk: {name}")
        if file_content_digest(path) != expected:
            raise ValueError(f"manifest artifact digest mismatch for {name}")


def assert_pf_handoff_certificate_id_matches_trace_certificate(release_root: Path) -> None:
    """``pf_handoff.certificate_id`` matches ``trace_certificate.json`` and certified bundle."""
    root = release_root.resolve()
    pf = _load(root / PF_HANDOFF_NAME)
    certificate = _load(root / "trace_certificate.json")
    if pf["certificate_id"] != certificate["certificate_id"]:
        raise ValueError("pf_handoff.certificate_id != trace_certificate.certificate_id")
    certified = _load(root / CERTIFIED_BUNDLE_NAME)
    if certified["certificates"][0]["certificate_id"] != pf["certificate_id"]:
        raise ValueError("pf_handoff.certificate_id != certified.certificates[0].certificate_id")


def assert_pf_handoff_trace_hash_matches_runtime_receipt(release_root: Path) -> None:
    """``pf_handoff.trace_hash`` matches trace, receipt, certificate, and certified bundle."""
    root = release_root.resolve()
    pf = _load(root / PF_HANDOFF_NAME)
    trace_hash = pf["trace_hash"]
    receipt = _load(root / "runtime_receipt.json")
    if receipt["trace_hash"] != trace_hash:
        raise ValueError("pf_handoff.trace_hash != runtime_receipt.trace_hash")
    _assert_trace_hash_stable(root, trace_hash)


def assert_pf_handoff_matches_release_manifest(release_root: Path | None = None) -> None:
    """``pf_handoff.json`` certificate_id, certified_bundle_hash, and trace_hash match ``manifest.json``."""
    from labtrust_gym.pcs.release_fixtures import release_dir

    root = (release_root or release_dir()).resolve()
    manifest = _load(root / MANIFEST_NAME)
    _assert_pf_handoff_matches_manifest(root, manifest)


def _assert_pf_handoff_matches_manifest(release_root: Path, manifest: dict[str, Any]) -> None:
    pf_path = release_root / PF_HANDOFF_NAME
    if not pf_path.is_file():
        raise FileNotFoundError(f"missing {PF_HANDOFF_NAME}")
    pf = _load(pf_path)
    if pf.get("certified_bundle") != CERTIFIED_BUNDLE_NAME:
        raise ValueError("pf_handoff.certified_bundle must be science_claim_bundle.certified.json")
    for key in ("certified_bundle_hash", "certificate_id", "trace_hash"):
        if pf.get(key) != manifest.get(key):
            raise ValueError(f"pf_handoff.{key} != manifest.{key}")


def verify_release_handoff(release_root: Path | None = None) -> list[str]:
    """
    Promotion guard: provenance, certificate-id propagation, trace-hash alignment, digests.

    Returns list of check labels that passed (for CI logging).
    """
    from labtrust_gym.pcs.release_fixtures import release_dir

    root = (release_root or release_dir()).resolve()
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing {MANIFEST_NAME}")

    manifest = _load(manifest_path)
    validate_release_manifest(manifest)
    validate_release_artifact_provenance(root, manifest)

    lt = manifest["labtrust_gym_commit"]
    ce = manifest["certifyedge_commit"]
    certificate = _load(root / "trace_certificate.json")
    assert_no_placeholder_commits(certificate["source_commit"], context="trace_certificate")
    if certificate["source_commit"] != ce:
        raise ValueError("trace_certificate.source_commit must equal manifest.certifyedge_commit")
    if certificate.get("source_repo") != CERTIFYEDGE_SOURCE_REPO:
        raise ValueError("trace_certificate.source_repo must be CertifyEdge")

    for bundle_name in ("science_claim_bundle.pending.json", CERTIFIED_BUNDLE_NAME):
        bundle = _load(root / bundle_name)
        for path, commit in labtrust_source_commit_paths(bundle):
            assert_no_placeholder_commits(commit, context=f"{bundle_name}.{path}")
            if commit != lt:
                raise ValueError(f"{bundle_name}.{path} source_commit must equal manifest.labtrust_gym_commit")

    cert_id = manifest["certificate_id"]
    trace_hash = manifest["trace_hash"]
    _assert_certificate_id_propagation(root, cert_id)
    _assert_trace_hash_stable(root, trace_hash)
    _assert_manifest_artifact_digests(root, manifest)

    certified_hash = file_content_digest(root / CERTIFIED_BUNDLE_NAME)
    if manifest.get("certified_bundle_hash") != certified_hash:
        raise ValueError("manifest.certified_bundle_hash != science_claim_bundle.certified.json digest")

    _assert_pf_handoff_matches_manifest(root, manifest)

    handoff_manifest_path = root / "handoff" / "RELEASE_HANDOFF_MANIFEST.json"
    if handoff_manifest_path.is_file():
        hm = _load(handoff_manifest_path)
        if hm.get("certificate_id") != cert_id or hm.get("trace_hash") != trace_hash:
            raise ValueError("handoff/RELEASE_HANDOFF_MANIFEST.json ids disagree with manifest.json")

    return [
        "labtrust_source_commits",
        "certifyedge_source_commit",
        "certificate_id_propagation",
        "trace_hash_alignment",
        "manifest_artifact_digests",
        "certified_bundle_hash",
        "pf_handoff",
    ]
