#!/usr/bin/env python3
"""Regenerate examples/pcs_qc_release/expected golden artifacts (requires git HEAD)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.provenance import resolve_source_commit


def main() -> int:
    commit, local_dev = resolve_source_commit(get_repo_root())
    if local_dev:
        print("error: golden generation requires a real git source_commit", file=sys.stderr)
        return 1

    exp = ROOT / "examples" / "pcs_qc_release" / "expected"
    exp.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "tmp_golden_gen"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()

    vd = tmp / "valid"
    run_demo("qc-release", out_dir=vd)
    export_trace(vd, exp / "valid_trace.json")
    export_runtime_receipt(vd, exp / "valid_runtime_receipt.json")
    export_pcs_bundle(vd, exp / "valid_science_claim_bundle.pending.json")
    receipt = json.loads((exp / "valid_runtime_receipt.json").read_text(encoding="utf-8"))
    pending = json.loads((exp / "valid_science_claim_bundle.pending.json").read_text(encoding="utf-8"))
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
        "signature_or_digest": "sha256:" + "a" * 64,
    }
    certified = attach_trace_certificate(pending, cert)
    (exp / "valid_science_claim_bundle.certified.json").write_text(
        json.dumps(certified, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    for demo, name in [
        ("qc-release-invalid-missing-qc", "invalid_missing_qc"),
        ("qc-release-invalid-unauthorized", "invalid_unauthorized"),
    ]:
        d = tmp / name
        run_demo(demo, out_dir=d)
        export_trace(d, exp / f"{name}_trace.json")
        meta = json.loads((d / "run_meta.json").read_text(encoding="utf-8"))
        (exp / f"{name}_result.json").write_text(
            json.dumps(
                {
                    "run_id": meta["run_id"],
                    "status": meta["status"],
                    "released": meta["released"],
                    "final_reason_code": meta["final_reason_code"],
                    "run_outcome": "failed",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    shutil.rmtree(tmp)
    print(f"golden artifacts written to {exp} (source_commit={commit[:12]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
