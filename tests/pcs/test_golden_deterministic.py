"""Golden PCS artifacts match deterministic fixture generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from labtrust_gym.pcs.validate import require_pcs_core, validate_runtime_receipt, validate_science_claim_bundle

pcs_core = pytest.importorskip("pcs_core")

EXPECTED = get_repo_root() / "examples" / "pcs_qc_release" / "expected"

GOLDEN_FILES = (
    "valid_trace.json",
    "valid_runtime_receipt.json",
    "valid_science_claim_bundle.pending.json",
    "valid_science_claim_bundle.certified.json",
    "trace_certificate.v0.json",
    "invalid_missing_qc_trace.json",
    "invalid_missing_qc_runtime_receipt.json",
    "invalid_missing_qc_result.json",
    "invalid_unauthorized_trace.json",
    "invalid_unauthorized_runtime_receipt.json",
    "invalid_unauthorized_result.json",
)


@pytest.fixture
def expected_dir() -> Path:
    if not EXPECTED.is_dir():
        pytest.skip("expected/ snapshots not present")
    return EXPECTED


def _load_golden(name: str, expected_dir: Path) -> dict:
    return json.loads((expected_dir / name).read_text(encoding="utf-8"))


def test_golden_artifacts_match_deterministic_generation(
    tmp_path: Path, expected_dir: Path, repo_root: Path
) -> None:
    require_pcs_core()
    for name in GOLDEN_FILES:
        assert (expected_dir / name).is_file(), f"missing golden {name}"

    with deterministic_mode():
        vd = tmp_path / "valid"
        run_demo("qc-release", out_dir=vd, policy_root=repo_root, deterministic=True)
        trace = export_trace(vd, tmp_path / "trace.json")
        receipt = export_runtime_receipt(vd, tmp_path / "receipt.json", policy_root=repo_root)
        pending = export_pcs_bundle(vd, tmp_path / "pending.json", policy_root=repo_root)
        cert = {
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
        certified = attach_trace_certificate(pending, cert)

        assert trace == _load_golden("valid_trace.json", expected_dir)
        assert receipt == _load_golden("valid_runtime_receipt.json", expected_dir)
        assert pending == _load_golden("valid_science_claim_bundle.pending.json", expected_dir)
        assert certified == _load_golden("valid_science_claim_bundle.certified.json", expected_dir)
        assert cert == _load_golden("trace_certificate.v0.json", expected_dir)

        for demo, prefix in [
            ("qc-release-invalid-missing-qc", "invalid_missing_qc"),
            ("qc-release-invalid-unauthorized", "invalid_unauthorized"),
        ]:
            d = tmp_path / prefix
            run_demo(demo, out_dir=d, policy_root=repo_root, deterministic=True)
            assert export_trace(d, tmp_path / f"{prefix}_trace.json") == _load_golden(
                f"{prefix}_trace.json", expected_dir
            )
            assert export_runtime_receipt(d, tmp_path / f"{prefix}_receipt.json", policy_root=repo_root) == _load_golden(
                f"{prefix}_runtime_receipt.json", expected_dir
            )
            meta = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
            result = {
                "run_id": meta["run_id"],
                "status": meta["status"],
                "released": meta["released"],
                "final_reason_code": meta["final_reason_code"],
                "run_outcome": "failed",
            }
            assert result == _load_golden(f"{prefix}_result.json", expected_dir)


@pytest.mark.parametrize(
    "filename",
    [
        "valid_runtime_receipt.json",
        "valid_science_claim_bundle.pending.json",
        "valid_science_claim_bundle.certified.json",
        "trace_certificate.v0.json",
        "invalid_missing_qc_runtime_receipt.json",
        "invalid_unauthorized_runtime_receipt.json",
    ],
)
def test_committed_golden_validates_against_pcs_core(expected_dir: Path, filename: str) -> None:
    require_pcs_core()
    artifact = _load_golden(filename, expected_dir)
    pcs_core.validate.validate_artifact(artifact)
    if artifact.get("certificate_id") and "trace_hash" in artifact:
        pcs_core.validate.validate_artifact(artifact)
    elif "bundle_id" in artifact:
        validate_science_claim_bundle(artifact)
    else:
        validate_runtime_receipt(artifact)
