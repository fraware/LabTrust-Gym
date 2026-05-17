"""PCS-core canonical ScienceClaimBundle shape (no PF legacy singular keys)."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt
from labtrust_gym.pcs.schema_version import assert_canonical_bundle_shape
from labtrust_gym.pcs.validate import require_pcs_core, validate_runtime_receipt, validate_science_claim_bundle

pcs_core = pytest.importorskip("pcs_core")


def test_runtime_receipt_validates_against_pcs_core(valid_run: Path, tmp_path: Path) -> None:
    require_pcs_core()
    receipt = export_runtime_receipt(valid_run, tmp_path / "runtime_receipt.json")
    validate_runtime_receipt(receipt)
    pcs_core.validate.validate_artifact(receipt)


def test_pending_bundle_uses_runtime_receipts_array(valid_run: Path, tmp_path: Path) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert isinstance(bundle["runtime_receipts"], list)
    assert len(bundle["runtime_receipts"]) == 1
    assert bundle["runtime_receipts"][0]["receipt_id"] == "receipt-qc-release"


def test_pending_bundle_does_not_emit_runtime_receipt_singular(valid_run: Path, tmp_path: Path) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert "runtime_receipt" not in bundle
    assert_canonical_bundle_shape(bundle)


def test_certified_bundle_uses_certificates_array(valid_run: Path, tmp_path: Path) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    receipt = pending["runtime_receipts"][0]
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
            "signature_or_digest": "sha256:" + "b" * 64,
        },
    )
    assert isinstance(certified["certificates"], list)
    assert len(certified["certificates"]) == 1
    assert "runtime_receipt" not in certified
    validate_science_claim_bundle(certified)
    pcs_core.validate.validate_artifact(certified)
