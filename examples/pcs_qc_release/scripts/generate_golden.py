#!/usr/bin/env python3
"""Regenerate examples/pcs_qc_release/expected golden artifacts (deterministic fixture mode)."""

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
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.deterministic import (
    DETERMINISTIC_CERT_DIGEST,
    DETERMINISTIC_CERT_SOURCE_COMMIT,
    DETERMINISTIC_CERTIFICATE_ID,
    deterministic_mode,
)
from labtrust_gym.pcs.ci_pipeline import validate_committed_goldens
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.validate import require_pcs_core


def _write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    exp = ROOT / "examples" / "pcs_qc_release" / "expected"
    exp.mkdir(parents=True, exist_ok=True)
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
        _write_json(exp / "trace_certificate.v0.json", cert)
        certified = attach_trace_certificate(pending, cert)
        _write_json(exp / "valid_science_claim_bundle.certified.json", certified)

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
    print(f"golden artifacts written to {exp} (PCS_DETERMINISTIC=1)")
    print(f"validated {len(validated)} golden files against pcs-core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
