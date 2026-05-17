"""RuntimeReceipt outcome fields and pcs-core alignment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.schema_version import SCHEMA_VERSION
from labtrust_gym.pcs.validate import (
    require_pcs_core,
    validate_runtime_receipt,
    validate_science_claim_bundle,
)

pcs_core = pytest.importorskip("pcs_core")


def test_runtime_receipt_includes_outcome_fields(valid_run: Path, tmp_path: Path) -> None:
    receipt = export_runtime_receipt(valid_run, tmp_path / "receipt.json")
    assert receipt["schema_version"] == SCHEMA_VERSION
    assert receipt["status"] == "RuntimeObserved"
    assert receipt["run_outcome"] == "passed"
    assert receipt["final_reason_code"] == "ok"
    assert receipt["released"] is True


def test_runtime_receipt_trace_hash_matches_trace(valid_run: Path, tmp_path: Path) -> None:
    export_trace(valid_run, tmp_path / "trace.json")
    receipt = export_runtime_receipt(valid_run, tmp_path / "receipt.json")
    trace = json.loads((valid_run / "trace.json").read_text(encoding="utf-8"))
    assert receipt["trace_hash"] == trace["trace_hash"]


def test_invalid_missing_qc_receipt_has_final_reason_code_missing_qc(missing_qc_run: Path, tmp_path: Path) -> None:
    receipt = export_runtime_receipt(missing_qc_run, tmp_path / "receipt.json")
    assert receipt["run_outcome"] == "failed"
    assert receipt["final_reason_code"] == "missing_qc"
    assert receipt["released"] is False
    assert receipt["status"] == "RuntimeObserved"


def test_invalid_unauthorized_receipt_has_final_reason_code_unauthorized_release(
    unauthorized_run: Path, tmp_path: Path
) -> None:
    receipt = export_runtime_receipt(unauthorized_run, tmp_path / "receipt.json")
    assert receipt["run_outcome"] == "failed"
    assert receipt["final_reason_code"] == "unauthorized_release"
    assert receipt["released"] is False


def test_pending_bundle_has_empty_certificates(valid_run: Path, tmp_path: Path) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert bundle["certificates"] == []
    assert bundle["claim_artifact"]["certificate_refs"] == []
    assert bundle["claim_artifact"]["status"] == "RuntimeObserved"


def test_attach_certificate_rejects_trace_hash_mismatch(valid_run: Path, tmp_path: Path) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    bad_cert = {
        "certificate_id": "cert-bad",
        "schema_version": "v0",
        "trace_hash": "sha256:" + "0" * 64,
    }
    with pytest.raises(ValueError, match="trace_hash"):
        attach_trace_certificate(bundle, bad_cert)


def test_attach_certificate_updates_claim_status_and_evidence_hashes(valid_run: Path, tmp_path: Path) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    receipt = bundle["runtime_receipts"][0]
    cert = {
        "certificate_id": "cert-trace-pcs-qc-release-v0.1",
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
        "source_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "signature_or_digest": "sha256:" + "e" * 64,
    }
    certified = attach_trace_certificate(bundle, cert)
    assert certified["claim_artifact"]["status"] == "CertificateChecked"
    assert certified["evidence_bundle"]["certificate_refs"] == ["cert-trace-pcs-qc-release-v0.1"]
    assert "cert-trace-pcs-qc-release-v0.1" in certified["evidence_bundle"]["artifact_hashes"]


def test_exported_artifacts_validate_against_pcs_core(valid_run: Path, tmp_path: Path) -> None:
    require_pcs_core()
    receipt = export_runtime_receipt(valid_run, tmp_path / "receipt.json")
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    validate_runtime_receipt(receipt)
    validate_science_claim_bundle(pending)

    certified = attach_trace_certificate(
        pending,
        {
            "certificate_id": "cert-trace-pcs-qc-release-v0.1",
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
            "source_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "signature_or_digest": "sha256:" + "f" * 64,
        },
    )
    validate_science_claim_bundle(certified)
