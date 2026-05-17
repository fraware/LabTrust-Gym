"""
PCS v0.1 release contract tests (required names for release-ready LabTrust-Gym).

Golden fixtures: examples/pcs_qc_release/expected/
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.deterministic import (
    DETERMINISTIC_CERT_DIGEST,
    DETERMINISTIC_CERT_SOURCE_COMMIT,
    DETERMINISTIC_CERTIFICATE_ID,
    deterministic_mode,
)
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.schema_version import LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS, assert_no_legacy_pf_bundle_keys
from labtrust_gym.pcs.validate import require_pcs_core, validate_runtime_receipt, validate_science_claim_bundle

pcs_core = pytest.importorskip("pcs_core")

RELEASE_GOLDEN_PCS_FILES = (
    "valid_runtime_receipt.json",
    "valid_science_claim_bundle.pending.json",
    "valid_science_claim_bundle.certified.json",
)


def _load_expected(expected_dir: Path, name: str) -> dict:
    return json.loads((expected_dir / name).read_text(encoding="utf-8"))


def _demo_certificate(receipt: dict) -> dict:
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


def test_runtime_receipt_validates_against_pcs_core(valid_run: Path, tmp_path: Path) -> None:
    require_pcs_core()
    receipt = export_runtime_receipt(valid_run, tmp_path / "runtime_receipt.json")
    validate_runtime_receipt(receipt)
    pcs_core.validate.validate_artifact(receipt)


def test_pending_bundle_validates_against_pcs_core(valid_run: Path, tmp_path: Path) -> None:
    require_pcs_core()
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    validate_science_claim_bundle(pending)
    pcs_core.validate.validate_artifact(pending)


def test_certified_bundle_validates_against_pcs_core(valid_run: Path, tmp_path: Path) -> None:
    require_pcs_core()
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    certified = attach_trace_certificate(pending, _demo_certificate(pending["runtime_receipts"][0]))
    validate_science_claim_bundle(certified)
    pcs_core.validate.validate_artifact(certified)


@pytest.mark.parametrize("filename", RELEASE_GOLDEN_PCS_FILES)
def test_committed_release_goldens_validate_with_pcs_validate(expected_dir: Path, filename: str) -> None:
    """Mirrors CI: pcs validate on committed release fixtures."""
    require_pcs_core()
    path = expected_dir / filename
    pcs_core.validate.validate_file(path)


def test_bundle_uses_runtime_receipts_array(valid_run: Path, tmp_path: Path) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert isinstance(bundle["runtime_receipts"], list)
    assert len(bundle["runtime_receipts"]) >= 1
    assert bundle["runtime_receipts"][0]["receipt_id"] == "receipt-qc-release"


def test_bundle_uses_certificates_array(valid_run: Path, tmp_path: Path) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert isinstance(pending["certificates"], list)
    certified = attach_trace_certificate(pending, _demo_certificate(pending["runtime_receipts"][0]))
    assert isinstance(certified["certificates"], list)
    assert len(certified["certificates"]) == 1


def test_bundle_does_not_emit_legacy_singular_fields(valid_run: Path, tmp_path: Path) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert_no_legacy_pf_bundle_keys(pending)
    for key in LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS:
        assert key not in pending
    certified = attach_trace_certificate(pending, _demo_certificate(pending["runtime_receipts"][0]))
    assert_no_legacy_pf_bundle_keys(certified)
    for key in LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS:
        assert key not in certified


def test_trace_hash_matches_runtime_receipt(valid_run: Path, tmp_path: Path) -> None:
    """CertifyEdge / Provability Fabric handoff: trace and receipt share trace_hash."""
    trace = export_trace(valid_run, tmp_path / "trace.json")
    receipt = export_runtime_receipt(valid_run, tmp_path / "runtime_receipt.json")
    assert receipt["trace_hash"] == trace["trace_hash"]
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert pending["runtime_receipts"][0]["trace_hash"] == trace["trace_hash"]


def test_trace_hash_matches_runtime_receipt_on_committed_goldens(expected_dir: Path) -> None:
    trace = _load_expected(expected_dir, "valid_trace.json")
    receipt = _load_expected(expected_dir, "valid_runtime_receipt.json")
    pending = _load_expected(expected_dir, "valid_science_claim_bundle.pending.json")
    alignment = _load_expected(expected_dir, "valid_trace_hash_alignment.json")
    th = trace["trace_hash"]
    assert receipt["trace_hash"] == th
    assert pending["runtime_receipts"][0]["trace_hash"] == th
    assert alignment["trace_hash"] == th
    assert alignment["runtime_receipt_trace_hash"] == th
    assert alignment["bundle_runtime_receipt_trace_hash"] == th


RELEASE_GOLDEN_FILES = (
    "valid_trace.json",
    "valid_runtime_receipt.json",
    "valid_science_claim_bundle.pending.json",
    "valid_science_claim_bundle.certified.json",
    "trace_certificate.v0.json",
    "valid_trace_hash_alignment.json",
    "invalid_missing_qc_trace.json",
    "invalid_missing_qc_runtime_receipt.json",
    "invalid_missing_qc_result.json",
    "invalid_unauthorized_trace.json",
    "invalid_unauthorized_runtime_receipt.json",
    "invalid_unauthorized_result.json",
)


def test_deterministic_mode_reproduces_expected_artifacts(
    tmp_path: Path, expected_dir: Path, repo_root: Path
) -> None:
    """Byte-stable deterministic release fixtures under examples/pcs_qc_release/expected/."""
    require_pcs_core()
    for name in RELEASE_GOLDEN_FILES:
        assert (expected_dir / name).is_file(), f"missing golden {name}"

    with deterministic_mode():
        vd = tmp_path / "valid"
        run_demo("qc-release", out_dir=vd, policy_root=repo_root, deterministic=True)
        trace = export_trace(vd, tmp_path / "trace.json")
        receipt = export_runtime_receipt(vd, tmp_path / "receipt.json", policy_root=repo_root)
        pending = export_pcs_bundle(vd, tmp_path / "pending.json", policy_root=repo_root)
        cert = _demo_certificate(receipt)
        certified = attach_trace_certificate(pending, cert)

        assert trace == _load_expected(expected_dir, "valid_trace.json")
        assert receipt == _load_expected(expected_dir, "valid_runtime_receipt.json")
        assert pending == _load_expected(expected_dir, "valid_science_claim_bundle.pending.json")
        assert certified == _load_expected(expected_dir, "valid_science_claim_bundle.certified.json")
        assert cert == _load_expected(expected_dir, "trace_certificate.v0.json")
        assert_no_legacy_pf_bundle_keys(pending)
        assert_no_legacy_pf_bundle_keys(certified)

        for demo, prefix in [
            ("qc-release-invalid-missing-qc", "invalid_missing_qc"),
            ("qc-release-invalid-unauthorized", "invalid_unauthorized"),
        ]:
            d = tmp_path / prefix
            run_demo(demo, out_dir=d, policy_root=repo_root, deterministic=True)
            assert export_trace(d, tmp_path / f"{prefix}_trace.json") == _load_expected(
                expected_dir, f"{prefix}_trace.json"
            )
            assert export_runtime_receipt(d, tmp_path / f"{prefix}_receipt.json", policy_root=repo_root) == _load_expected(
                expected_dir, f"{prefix}_runtime_receipt.json"
            )
            meta = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
            result = {
                "run_id": meta["run_id"],
                "status": meta["status"],
                "released": meta["released"],
                "final_reason_code": meta["final_reason_code"],
                "run_outcome": "failed",
            }
            assert result == _load_expected(expected_dir, f"{prefix}_result.json")


def test_invalid_missing_qc_has_final_reason_code_missing_qc(missing_qc_run: Path, tmp_path: Path) -> None:
    meta = json.loads((missing_qc_run / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["final_reason_code"] == "missing_qc"
    assert meta["released"] is False
    receipt = export_runtime_receipt(missing_qc_run, tmp_path / "receipt.json")
    assert receipt["run_outcome"] == "failed"
    assert receipt["final_reason_code"] == "missing_qc"
    assert receipt["status"] == "RuntimeObserved"


def test_invalid_unauthorized_has_final_reason_code_unauthorized_release(
    unauthorized_run: Path, tmp_path: Path
) -> None:
    meta = json.loads((unauthorized_run / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["final_reason_code"] == "unauthorized_release"
    assert meta["released"] is False
    receipt = export_runtime_receipt(unauthorized_run, tmp_path / "receipt.json")
    assert receipt["run_outcome"] == "failed"
    assert receipt["final_reason_code"] == "unauthorized_release"
    assert receipt["status"] == "RuntimeObserved"
