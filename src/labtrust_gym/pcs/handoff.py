"""Export cross-repo handoff artifact bundles (CertifyEdge, Provability Fabric)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import deterministic_mode, is_deterministic_mode
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.integrity import validate_run_directory
from labtrust_gym.pcs.validate import validate_pcs_artifact, validate_science_claim_bundle

CERTIFYEDGE_TRACES: list[tuple[str, str]] = [
    ("valid_trace.json", "qc-release"),
    ("invalid_missing_qc_trace.json", "qc-release-invalid-missing-qc"),
    ("invalid_unauthorized_trace.json", "qc-release-invalid-unauthorized"),
]


def export_handoff_bundle(
    out_dir: Path,
    *,
    policy_root: Path | None = None,
    work_dir: Path | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """
    Run all three PCS demos and write handoff artifacts.

    Layout:
      <out>/certifyedge/*.json
      <out>/provability_fabric/* (valid run exports)
      <out>/manifest.json
    """
    root = policy_root or get_repo_root()
    out_dir = Path(out_dir)
    work = Path(work_dir) if work_dir else out_dir / "_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    certify_dir = out_dir / "certifyedge"
    pf_dir = out_dir / "provability_fabric"
    certify_dir.mkdir(parents=True, exist_ok=True)
    pf_dir.mkdir(parents=True, exist_ok=True)

    use_deterministic = is_deterministic_mode()
    manifest: dict[str, Any] = {
        "handoff_version": "v0.1",
        "deterministic": use_deterministic,
        "scenarios": {},
    }

    bundle: dict[str, Any]
    with deterministic_mode(enabled=use_deterministic):
        for filename, demo in CERTIFYEDGE_TRACES:
            run_dir = work / demo.replace("-", "_")
            run_demo(demo, out_dir=run_dir, policy_root=root, deterministic=use_deterministic)
            export_trace(run_dir, certify_dir / filename)
            if validate:
                errs = validate_run_directory(run_dir)
                if errs:
                    raise ValueError(f"handoff validation failed for {demo}: " + "; ".join(errs))
            manifest["scenarios"][demo] = {"trace": f"certifyedge/{filename}", "run_dir": str(run_dir)}

        valid_dir = work / "qc_release"
        run_demo("qc-release", out_dir=valid_dir, policy_root=root, deterministic=use_deterministic)
        export_trace(valid_dir, pf_dir / "trace.json")
        receipt = export_runtime_receipt(valid_dir, pf_dir / "runtime_receipt.json", policy_root=root)
        bundle = export_pcs_bundle(valid_dir, pf_dir / "science_claim_bundle.pending.json", policy_root=root)
        if validate:
            validate_pcs_artifact(receipt)
            validate_science_claim_bundle(bundle)
            errs = validate_run_directory(valid_dir)
            if errs:
                raise ValueError("valid run integrity: " + "; ".join(errs))

    manifest["provability_fabric"] = {
        "trace": "provability_fabric/trace.json",
        "runtime_receipt": "provability_fabric/runtime_receipt.json",
        "science_claim_bundle_pending": "provability_fabric/science_claim_bundle.pending.json",
        "claim_id": bundle["claim_artifact"]["artifact_id"],
        "limitations_doc": "docs/pcs_limitations.md",
    }
    manifest["trace_hash_rule"] = "docs/pcs_trace_model.md#trace-hash"

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if work_dir is None and work.exists():
        shutil.rmtree(work)

    return manifest
