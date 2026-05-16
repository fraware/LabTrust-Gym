"""Attach TraceCertificate to ScienceClaimBundle."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.attach_certificate import attach_certificate_files
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt
from labtrust_gym.pcs.validate import validate_pcs_artifact


def test_attach_certificate_updates_bundle(valid_run: Path, tmp_path: Path) -> None:
    pending = tmp_path / "pending.json"
    bundle = export_pcs_bundle(valid_run, pending)
    receipt = export_runtime_receipt(valid_run, tmp_path / "receipt.json")
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
        "signature_or_digest": "sha256:" + "c" * 64,
    }
    cert_path = tmp_path / "trace_certificate.json"
    cert_path.write_text(json.dumps(cert, indent=2) + "\n", encoding="utf-8")
    out = tmp_path / "certified.json"
    certified = attach_certificate_files(pending, cert_path, out)
    validate_pcs_artifact(certified)
    assert len(certified["certificates"]) == 1
    assert certified["claim_artifact"]["certificate_refs"] == ["cert-trace-pcs-qc-release-v0.1"]
    assert certified["certificates"][0]["trace_hash"] == receipt["trace_hash"]
