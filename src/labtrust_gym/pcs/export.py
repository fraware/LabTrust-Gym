"""Export PCS artifacts from a demo run directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.runtime_receipt import build_runtime_receipt
from labtrust_gym.pcs.science_claim_bundle import build_science_claim_bundle


def _write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def export_trace(run_dir: Path, out_path: Path) -> dict[str, Any]:
    trace_path = run_dir / "trace.json"
    if not trace_path.is_file():
        raise FileNotFoundError(f"trace not found: {trace_path}")
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    _write_json(out_path, trace)
    return trace


def export_runtime_receipt(
    run_dir: Path,
    out_path: Path,
    *,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    receipt = build_runtime_receipt(run_dir, policy_root=policy_root)
    _write_json(out_path, receipt)
    pcs_dir = run_dir / "pcs"
    pcs_dir.mkdir(parents=True, exist_ok=True)
    _write_json(pcs_dir / "runtime_receipt.json", receipt)
    return receipt


def export_pcs_bundle(
    run_dir: Path,
    out_path: Path,
    *,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    bundle = build_science_claim_bundle(run_dir, policy_root=policy_root)
    _write_json(out_path, bundle)
    pcs_dir = run_dir / "pcs"
    pcs_dir.mkdir(parents=True, exist_ok=True)
    _write_json(pcs_dir / "science_claim_bundle.pending.json", bundle)
    _write_json(pcs_dir / "evidence_bundle.json", bundle["evidence_bundle"])
    return bundle
