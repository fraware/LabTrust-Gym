"""Cross-repo PCS v0.1 release candidate fixtures (real CertifyEdge certificate)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.manifest import validate_release_manifest
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

MANIFEST_NAME = "manifest.json"


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
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_release_manifest(manifest)
        ok.append(MANIFEST_NAME)

    th = receipt["trace_hash"]
    if trace["trace_hash"] != th:
        raise ValueError("release trace.trace_hash != runtime_receipt.trace_hash")
    if pending["runtime_receipts"][0]["trace_hash"] != th:
        raise ValueError("release pending bundle trace_hash != runtime_receipt.trace_hash")
    if certificate["trace_hash"] != th:
        raise ValueError("release certificate trace_hash != runtime_receipt.trace_hash")
    if certified["certificates"][0]["trace_hash"] != th:
        raise ValueError("release certified bundle certificate trace_hash mismatch")

    for name in RELEASE_ARTIFACTS:
        ok.append(name)
    return ok
