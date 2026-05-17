"""Cross-repo PCS v0.1 release candidate fixtures (real CertifyEdge certificate)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.manifest import validate_release_manifest
from labtrust_gym.pcs.release_provenance import validate_release_artifact_provenance
from labtrust_gym.pcs.release_run import (
    HANDOFF_FOR_PF_NAME,
    RELEASE_HANDOFF_MANIFEST_NAME,
    validate_certificate_id_chain,
    validate_handoff_directory,
)
from labtrust_gym.pcs.mock_certificate import CERTIFYEDGE_SOURCE_REPO, is_mock_certificate
from labtrust_gym.pcs.deterministic import DETERMINISTIC_CERTIFICATE_ID
from labtrust_gym.pcs.schema_version import assert_no_legacy_pf_bundle_keys
from labtrust_gym.pcs.validate import (
    require_pcs_core,
    validate_runtime_receipt,
    validate_science_claim_bundle,
    validate_trace,
)

RELEASE_REL = Path("examples/pcs_qc_release/release")

RELEASE_ARTIFACTS = (
    "trace.json",
    "runtime_receipt.json",
    "trace_certificate.json",
    "science_claim_bundle.pending.json",
    "science_claim_bundle.certified.json",
)

TRACE_HASH_ALIGNMENT_NAME = "trace_hash_alignment.json"
MANIFEST_NAME = "manifest.json"
EXPECTED_REL = Path("examples/pcs_qc_release/expected")
VALID_EXPECTED_TRACE = "valid_trace.json"


def release_dir(policy_root: Path | None = None) -> Path:
    return (policy_root or get_repo_root()) / RELEASE_REL


def release_fixture_present(root: Path | None = None) -> bool:
    directory = release_dir(root)
    return (
        (directory / "trace_certificate.json").is_file()
        and (directory / "science_claim_bundle.certified.json").is_file()
        and (directory / MANIFEST_NAME).is_file()
    )


def _load(directory: Path, name: str) -> dict[str, Any]:
    return json.loads((directory / name).read_text(encoding="utf-8"))


def write_trace_hash_alignment(release_root: Path) -> dict[str, Any]:
    """Write trace_hash_alignment.json for CertifyEdge / PF handoff checks."""
    trace = _load(release_root, "trace.json")
    receipt = _load(release_root, "runtime_receipt.json")
    pending = _load(release_root, "science_claim_bundle.pending.json")
    doc = {
        "schema_version": "v0",
        "property_id": "pcs.qc_release.trace_hash_alignment",
        "trace_hash": trace["trace_hash"],
        "runtime_receipt_trace_hash": receipt["trace_hash"],
        "bundle_runtime_receipt_trace_hash": pending["runtime_receipts"][0]["trace_hash"],
    }
    path = release_root / TRACE_HASH_ALIGNMENT_NAME
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def assert_release_trace_matches_expected_goldens(
    release_root: Path | None = None,
    *,
    policy_root: Path | None = None,
) -> None:
    """Release trace must match LabTrust-local deterministic golden (same PCS_DETERMINISTIC=1 run)."""
    root = release_root or release_dir(policy_root)
    expected = (policy_root or get_repo_root()) / EXPECTED_REL / VALID_EXPECTED_TRACE
    if not expected.is_file():
        raise FileNotFoundError(f"missing expected golden {expected}")
    release_trace = _load(root, "trace.json")
    golden_trace = json.loads(expected.read_text(encoding="utf-8"))
    if release_trace["trace_hash"] != golden_trace["trace_hash"]:
        raise ValueError(
            "release/ trace_hash must match expected/valid_trace.json "
            f"({release_trace['trace_hash']!r} != {golden_trace['trace_hash']!r})"
        )


def validate_release_fixtures(directory: Path | None = None) -> list[str]:
    """
    Validate committed ``release/`` artifacts (real CertifyEdge certificate required).

    Raises if mock certificate digest or missing files.
    """
    require_pcs_core()
    from pcs_core.validate import validate_artifact

    root = directory or release_dir()
    if not root.is_dir():
        raise FileNotFoundError(f"release directory not found: {root}")

    ok: list[str] = []
    for name in RELEASE_ARTIFACTS:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"release fixture missing: {name}")

    trace = _load(root, "trace.json")
    receipt = _load(root, "runtime_receipt.json")
    certificate = _load(root, "trace_certificate.json")
    pending = _load(root, "science_claim_bundle.pending.json")
    certified = _load(root, "science_claim_bundle.certified.json")

    validate_trace(trace)
    validate_runtime_receipt(receipt)
    validate_artifact(receipt)
    validate_science_claim_bundle(pending)
    validate_artifact(pending)
    validate_artifact(certificate)
    validate_science_claim_bundle(certified)
    validate_artifact(certified)

    assert_no_legacy_pf_bundle_keys(pending)
    assert_no_legacy_pf_bundle_keys(certified)

    if is_mock_certificate(certificate):
        raise ValueError(
            "release/trace_certificate.json must be CertifyEdge CLI output, "
            "not LabTrust mock certificate (DETERMINISTIC_CERT_DIGEST)"
        )
    if certificate.get("source_repo") != CERTIFYEDGE_SOURCE_REPO:
        raise ValueError("release certificate source_repo must be CertifyEdge")
    producer = str(certificate.get("producer", "")).lower()
    if producer != "certifyedge":
        raise ValueError(f"release certificate producer must be CertifyEdge, got {certificate.get('producer')!r}")
    if certificate.get("certificate_id") == DETERMINISTIC_CERTIFICATE_ID:
        raise ValueError("release certificate_id must not be LabTrust mock fixture id")

    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"release fixture missing: {MANIFEST_NAME}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_release_manifest(manifest)
    validate_release_artifact_provenance(root, manifest)
    ok.append(MANIFEST_NAME)

    alignment_path = root / TRACE_HASH_ALIGNMENT_NAME
    if alignment_path.is_file():
        alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
        th = receipt["trace_hash"]
        if alignment["trace_hash"] != th or alignment["runtime_receipt_trace_hash"] != th:
            raise ValueError(f"{TRACE_HASH_ALIGNMENT_NAME}: trace_hash mismatch")
        ok.append(TRACE_HASH_ALIGNMENT_NAME)

    assert_release_trace_matches_expected_goldens(root)

    th = receipt["trace_hash"]
    if trace["trace_hash"] != th:
        raise ValueError("release trace.trace_hash != runtime_receipt.trace_hash")
    if pending["runtime_receipts"][0]["trace_hash"] != th:
        raise ValueError("release pending bundle trace_hash != runtime_receipt.trace_hash")
    if certificate["trace_hash"] != th:
        raise ValueError("release certificate trace_hash != runtime_receipt.trace_hash")
    if certified["certificates"][0]["trace_hash"] != th:
        raise ValueError("release certified bundle certificate trace_hash mismatch")

    handoff_root = root / "handoff"
    if handoff_root.is_dir():
        validate_handoff_directory(handoff_root)
        ok.append("handoff/")
        if (handoff_root / HANDOFF_FOR_PF_NAME).is_file():
            ok.append(f"handoff/{HANDOFF_FOR_PF_NAME}")
        if (handoff_root / RELEASE_HANDOFF_MANIFEST_NAME).is_file():
            ok.append(f"handoff/{RELEASE_HANDOFF_MANIFEST_NAME}")

    signed = root / "signed_science_claim_bundle.json"
    if signed.is_file():
        validate_certificate_id_chain(root)
        ok.append("signed_science_claim_bundle.json")

    for name in RELEASE_ARTIFACTS:
        ok.append(name)
    return ok
