#!/usr/bin/env python3
"""Regenerate examples/pcs_qc_release/expected LabTrust-local deterministic fixtures."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

os.environ["PCS_DETERMINISTIC"] = "1"

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.ci_pipeline import validate_committed_goldens
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.deterministic import deterministic_mode
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.mock_certificate import MOCK_CERTIFICATE_BASENAME, build_mock_trace_certificate
from labtrust_gym.pcs.validate import require_pcs_core


def _write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    exp = ROOT / "examples" / "pcs_qc_release" / "expected"
    exp.mkdir(parents=True, exist_ok=True)
    mock_cert_path = exp / MOCK_CERTIFICATE_BASENAME
    legacy_mock = exp / "trace_certificate.v0.json"
    if legacy_mock.is_file() and not mock_cert_path.is_file():
        legacy_mock.rename(mock_cert_path)
    elif legacy_mock.is_file():
        legacy_mock.unlink()

    tmp = ROOT / "tmp_golden_gen"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    root = get_repo_root()

    with deterministic_mode():
        vd = tmp / "valid"
        run_demo("qc-release", out_dir=vd, policy_root=root, deterministic=True)
        export_trace(vd, exp / "valid_trace.json")
        export_runtime_receipt(vd, exp / "valid_runtime_receipt.json", policy_root=root)
        export_pcs_bundle(vd, exp / "valid_science_claim_bundle.pending.json", policy_root=root)
        receipt = json.loads((exp / "valid_runtime_receipt.json").read_text(encoding="utf-8"))
        pending = json.loads((exp / "valid_science_claim_bundle.pending.json").read_text(encoding="utf-8"))
        cert = build_mock_trace_certificate(receipt)
        _write_json(mock_cert_path, cert)
        certified = attach_trace_certificate(pending, cert)
        _write_json(exp / "valid_science_claim_bundle.certified.json", certified)
        trace = json.loads((exp / "valid_trace.json").read_text(encoding="utf-8"))
        _write_json(
            exp / "valid_trace_hash_alignment.json",
            {
                "schema_version": "v0",
                "property_id": "pcs.qc_release.trace_hash_alignment",
                "trace_hash": trace["trace_hash"],
                "runtime_receipt_trace_hash": receipt["trace_hash"],
                "bundle_runtime_receipt_trace_hash": pending["runtime_receipts"][0]["trace_hash"],
            },
        )

        for demo, prefix in [
            ("qc-release-invalid-missing-qc", "invalid_missing_qc"),
            ("qc-release-invalid-unauthorized", "invalid_unauthorized"),
        ]:
            d = tmp / prefix
            run_demo(demo, out_dir=d, policy_root=root, deterministic=True)
            export_trace(d, exp / f"{prefix}_trace.json")
            export_runtime_receipt(d, exp / f"{prefix}_runtime_receipt.json", policy_root=root)
            meta = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
            _write_json(
                exp / f"{prefix}_result.json",
                {
                    "run_id": meta["run_id"],
                    "status": meta["status"],
                    "released": meta["released"],
                    "final_reason_code": meta["final_reason_code"],
                    "run_outcome": "failed",
                },
            )

    shutil.rmtree(tmp)
    require_pcs_core()
    validated = validate_committed_goldens(exp)
    print(f"LabTrust-local goldens written to {exp} (PCS_DETERMINISTIC=1)")
    print(f"mock certificate: {MOCK_CERTIFICATE_BASENAME} (not for release/)")
    print(f"validated {len(validated)} files against pcs-core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
