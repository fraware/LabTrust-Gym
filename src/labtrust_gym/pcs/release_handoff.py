"""Canonical LabTrust release handoff manifest and promotion guards for pcs-core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.handoff_manifest import (
    CERTIFIED_BUNDLE_NAME,
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    assert_handoff_manifest_valid,
    build_handoff_to_certifyedge_from_release,
    build_handoff_to_pf_from_release,
)
from labtrust_gym.pcs.release_fragment import (
    LABTRUST_RELEASE_FRAGMENT_NAME,
    emit_labtrust_release_fragment,
)
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
)

MANIFEST_NAME = "manifest.json"
# Legacy alias retained for tests/docs migrating from pf_handoff.json
PF_HANDOFF_NAME = HANDOFF_TO_PF_NAME


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
    """Write Phase 2 handoffs and component release fragment under ``release/``."""
    build_handoff_to_certifyedge_from_release(release_root, manifest)
    handoff = build_handoff_to_pf_from_release(release_root, manifest)
    emit_labtrust_release_fragment(
        release_dir=release_root,
        source_commit=manifest.get("labtrust_gym_commit"),
    )
    return handoff


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


def _load_handoff_to_pf(release_root: Path) -> dict[str, Any]:
    path = release_root / HANDOFF_TO_PF_NAME
    if not path.is_file():
        raise FileNotFoundError(f"missing {HANDOFF_TO_PF_NAME}")
    doc = _load(path)
    assert_handoff_manifest_valid(doc)
    return doc


def assert_handoff_to_pf_certificate_id_matches_trace_certificate(release_root: Path) -> None:
    """HandoffManifest invariants.certificate_id matches trace and certified bundle."""
    root = release_root.resolve()
    handoff = _load_handoff_to_pf(root)
    certificate_id = handoff["invariants"]["certificate_id"]
    certificate = _load(root / "trace_certificate.json")
    if certificate["certificate_id"] != certificate_id:
        raise ValueError("handoff invariants.certificate_id != trace_certificate.certificate_id")
    certified = _load(root / CERTIFIED_BUNDLE_NAME)
    if certified["certificates"][0]["certificate_id"] != certificate_id:
        raise ValueError("handoff invariants.certificate_id != certified.certificates[0].certificate_id")


def assert_handoff_to_pf_trace_hash_matches_runtime_receipt(release_root: Path) -> None:
    """HandoffManifest invariants.trace_hash matches runtime receipt and chain."""
    root = release_root.resolve()
    handoff = _load_handoff_to_pf(root)
    trace_hash = handoff["invariants"]["trace_hash"]
    receipt = _load(root / "runtime_receipt.json")
    if receipt["trace_hash"] != trace_hash:
        raise ValueError("handoff invariants.trace_hash != runtime_receipt.trace_hash")
    _assert_trace_hash_stable(root, trace_hash)


def assert_handoff_to_pf_bundle_hash_matches_certified_bundle(release_root: Path) -> None:
    """HandoffManifest input artifact and invariant hashes match certified bundle file."""
    root = release_root.resolve()
    handoff = _load_handoff_to_pf(root)
    bundle_path = root / CERTIFIED_BUNDLE_NAME
    on_disk = file_content_digest(bundle_path)
    entry = handoff["input_artifacts"][CERTIFIED_BUNDLE_NAME]
    if entry["sha256"] != on_disk:
        raise ValueError("handoff input_artifacts certified bundle sha256 != file digest")
    if handoff["invariants"]["certified_bundle_hash"] != on_disk:
        raise ValueError("handoff invariants.certified_bundle_hash != certified bundle file digest")


# Backward-compatible aliases for RC gate tests
assert_pf_handoff_certificate_id_matches_trace_certificate = (
    assert_handoff_to_pf_certificate_id_matches_trace_certificate
)
assert_pf_handoff_trace_hash_matches_runtime_receipt = assert_handoff_to_pf_trace_hash_matches_runtime_receipt


def assert_pf_handoff_matches_release_manifest(release_root: Path | None = None) -> None:
    """``handoff_to_pf.json`` invariants match ``manifest.json``."""
    from labtrust_gym.pcs.release_fixtures import release_dir

    root = (release_root or release_dir()).resolve()
    manifest = _load(root / MANIFEST_NAME)
    _assert_handoff_to_pf_matches_manifest(root, manifest)


def _assert_handoff_to_pf_matches_manifest(release_root: Path, manifest: dict[str, Any]) -> None:
    handoff = _load_handoff_to_pf(release_root)
    invariants = handoff.get("invariants") or {}
    for key in ("certified_bundle_hash", "certificate_id", "trace_hash"):
        if invariants.get(key) != manifest.get(key):
            raise ValueError(f"handoff.invariants.{key} != manifest.{key}")
    certified_entry = handoff["input_artifacts"].get(CERTIFIED_BUNDLE_NAME) or {}
    if certified_entry.get("sha256") != manifest.get("certified_bundle_hash"):
        raise ValueError("handoff input certified bundle sha256 != manifest.certified_bundle_hash")
    if handoff.get("handoff_kind") != "bundle_to_verifier":
        raise ValueError("handoff_to_pf handoff_kind must be bundle_to_verifier")


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

    _assert_handoff_to_pf_matches_manifest(root, manifest)
    assert_handoff_to_pf_bundle_hash_matches_certified_bundle(root)

    ce_handoff_path = root / HANDOFF_TO_CERTIFYEDGE_NAME
    if not ce_handoff_path.is_file():
        raise FileNotFoundError(f"missing {HANDOFF_TO_CERTIFYEDGE_NAME}")
    ce_handoff = _load(ce_handoff_path)
    assert_handoff_manifest_valid(ce_handoff)
    if ce_handoff.get("handoff_kind") != "runtime_to_certificate":
        raise ValueError("handoff_to_certifyedge handoff_kind must be runtime_to_certificate")
    if ce_handoff.get("invariants", {}).get("trace_hash") != trace_hash:
        raise ValueError("handoff_to_certifyedge invariants.trace_hash != manifest.trace_hash")

    handoff_sub = root / "handoff"
    for name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME):
        sub_path = handoff_sub / name
        if sub_path.is_file() and file_content_digest(sub_path) != file_content_digest(root / name):
            raise ValueError(f"handoff/{name} digest != release/{name}")

    fragment_path = root / LABTRUST_RELEASE_FRAGMENT_NAME
    if fragment_path.is_file():
        from labtrust_gym.pcs.release_fragment import (
            assert_release_fragment_source_commit_matches_artifacts,
            assert_release_fragment_valid,
        )

        fragment = _load(fragment_path)
        assert_release_fragment_valid(fragment)
        assert_release_fragment_source_commit_matches_artifacts(root, fragment)
        if fragment.get("source_commit") != lt:
            raise ValueError("labtrust_release_fragment.source_commit != manifest.labtrust_gym_commit")

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
        "handoff_to_pf",
        "handoff_to_certifyedge",
        "labtrust_release_fragment",
    ]
