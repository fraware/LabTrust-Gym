"""Deterministic PCS export + validation pipeline (CI, pytest, golden regeneration)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.deterministic import (
    DETERMINISTIC_CERT_DIGEST,
    DETERMINISTIC_CERT_SOURCE_COMMIT,
    DETERMINISTIC_CERTIFICATE_ID,
    deterministic_mode,
)
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.schema_version import assert_no_legacy_pf_bundle_keys
from labtrust_gym.pcs.validate import (
    require_pcs_core,
    validate_run_dir,
    validate_runtime_receipt,
    validate_science_claim_bundle,
    validate_trace,
)

EXPECTED_REL = Path("examples/pcs_qc_release/expected")

GOLDEN_PCS_ARTIFACTS = (
    "valid_runtime_receipt.json",
    "valid_science_claim_bundle.pending.json",
    "valid_science_claim_bundle.certified.json",
    "trace_certificate.v0.json",
    "invalid_missing_qc_runtime_receipt.json",
    "invalid_unauthorized_runtime_receipt.json",
)

GOLDEN_TRACE_FILES = (
    "valid_trace.json",
    "invalid_missing_qc_trace.json",
    "invalid_unauthorized_trace.json",
)

GOLDEN_BUNDLE_FILES = (
    "valid_science_claim_bundle.pending.json",
    "valid_science_claim_bundle.certified.json",
)


@dataclass(frozen=True)
class PcsExportArtifacts:
    """Paths and in-memory docs from a deterministic qc-release export run."""

    run_dir: Path
    trace_path: Path
    receipt_path: Path
    pending_path: Path
    certified_path: Path
    trace: dict[str, Any]
    receipt: dict[str, Any]
    pending: dict[str, Any]
    certified: dict[str, Any]


def expected_dir(policy_root: Path | None = None) -> Path:
    return (policy_root or get_repo_root()) / EXPECTED_REL


def deterministic_trace_certificate(receipt: dict[str, Any]) -> dict[str, Any]:
    """CertifyEdge-shaped TraceCertificate.v0 for demo attach (deterministic fields)."""
    return {
        "certificate_id": DETERMINISTIC_CERTIFICATE_ID,
        "schema_version": "v0",
        "trace_hash": receipt["trace_hash"],
        "spec_hash": receipt["input_hashes"]["workflow"],
        "property_id": "pcs.qc_release.protocol_safety",
        "checker": "certifyedge",
        "checker_version": "0.1.0",
        "status": "CertificateChecked",
        "counterexample_ref": None,
        "created_at": receipt["ended_at"],
        "producer": "certifyedge",
        "producer_version": "0.1.0",
        "source_repo": "https://github.com/fraware/CertifyEdge",
        "source_commit": DETERMINISTIC_CERT_SOURCE_COMMIT,
        "signature_or_digest": DETERMINISTIC_CERT_DIGEST,
    }


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_export_artifacts(
    *,
    trace: dict[str, Any],
    receipt: dict[str, Any],
    pending: dict[str, Any],
    certified: dict[str, Any] | None = None,
) -> None:
    """LabTrust integrity + pcs-core schema + canonical bundle shape."""
    require_pcs_core()
    from pcs_core.validate import validate_artifact

    validate_trace(trace)
    validate_runtime_receipt(receipt)
    validate_science_claim_bundle(pending)
    validate_artifact(receipt)
    validate_artifact(pending)
    assert_no_legacy_pf_bundle_keys(pending)
    if pending["runtime_receipts"][0]["trace_hash"] != receipt["trace_hash"]:
        raise ValueError("pending runtime_receipts[0].trace_hash != receipt.trace_hash")
    if trace.get("trace_hash") != receipt["trace_hash"]:
        raise ValueError("trace.trace_hash != receipt.trace_hash")
    if certified is not None:
        validate_science_claim_bundle(certified)
        validate_artifact(certified)
        assert_no_legacy_pf_bundle_keys(certified)


def run_deterministic_qc_release_export(
    work_parent: Path,
    *,
    policy_root: Path | None = None,
    run_name: str = "pcs-qcrelease-valid",
) -> PcsExportArtifacts:
    """
    Run qc-release in deterministic mode, export PCS artifacts, attach certificate.

    Used by CI and ``tests/pcs/test_ci_pipeline.py`` (single source of truth with shell wrappers).
    """
    require_pcs_core()
    root = policy_root or get_repo_root()
    run_dir = work_parent / run_name
    trace_path = work_parent / "trace.json"
    receipt_path = work_parent / "runtime_receipt.json"
    pending_path = work_parent / "science_claim_bundle.pending.json"
    certified_path = work_parent / "science_claim_bundle.certified.json"

    with deterministic_mode():
        run_demo("qc-release", out_dir=run_dir, policy_root=root, deterministic=True)
        trace = export_trace(run_dir, trace_path)
        receipt = export_runtime_receipt(run_dir, receipt_path, policy_root=root)
        pending = export_pcs_bundle(run_dir, pending_path, policy_root=root)
        validate_run_dir(run_dir)
        cert = deterministic_trace_certificate(receipt)
        certified = attach_trace_certificate(pending, cert)
        _write_json(certified_path, certified)

    validate_export_artifacts(trace=trace, receipt=receipt, pending=pending, certified=certified)
    return PcsExportArtifacts(
        run_dir=run_dir,
        trace_path=trace_path,
        receipt_path=receipt_path,
        pending_path=pending_path,
        certified_path=certified_path,
        trace=trace,
        receipt=receipt,
        pending=pending,
        certified=certified,
    )


def validate_committed_goldens(exp: Path | None = None) -> list[str]:
    """pcs-core + LabTrust checks on committed ``expected/`` snapshots."""
    require_pcs_core()
    from pcs_core.validate import validate_artifact

    directory = exp or expected_dir()
    if not directory.is_dir():
        raise FileNotFoundError(f"golden directory not found: {directory}")

    ok: list[str] = []
    for name in GOLDEN_TRACE_FILES:
        trace = json.loads((directory / name).read_text(encoding="utf-8"))
        validate_trace(trace)
        ok.append(name)

    for name in GOLDEN_PCS_ARTIFACTS:
        data = json.loads((directory / name).read_text(encoding="utf-8"))
        validate_artifact(data)
        if "bundle_id" in data:
            validate_science_claim_bundle(data)
            assert_no_legacy_pf_bundle_keys(data)
        elif "receipt_id" in data:
            validate_runtime_receipt(data)
        ok.append(name)

    for name in ("invalid_missing_qc_result.json", "invalid_unauthorized_result.json"):
        path = directory / name
        if not path.is_file():
            raise FileNotFoundError(name)
        meta = json.loads(path.read_text(encoding="utf-8"))
        if meta.get("run_outcome") != "failed":
            raise ValueError(f"{name}: run_outcome must be failed")
        ok.append(name)

    return ok


def ci_work_parent() -> Path:
    raw = os.environ.get("PCS_CI_WORK_PARENT", "/tmp/pcs-ci-work")
    return Path(raw)
