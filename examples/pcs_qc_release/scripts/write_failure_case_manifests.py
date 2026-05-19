#!/usr/bin/env python3
"""Write failure_case_manifest.json for each gallery case (no PCS imports)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GALLERY = ROOT / "examples" / "pcs_qc_release" / "failures"
PROFILE = json.loads(
    (ROOT / "examples" / "pcs_qc_release" / "workflow_profile.v0.json").read_text(encoding="utf-8")
)
WORKFLOW_ID = PROFILE["workflow_id"]

RESPONSIBLE = {
    "missing_qc_result": "workflow.runtime",
    "unauthorized_release": "workflow.runtime",
    "trace_hash_tamper": "workflow.handoff",
    "certificate_id_tamper": "certifyedge.certificate",
    "stale_trace_after_certificate": "workflow.status_policy",
    "legacy_handoff_file": "workflow.handoff",
    "placeholder_commit": "workflow.provenance",
    "lean_trace_hash_mismatch": "lean.extraction",
    "lean_rejected_certificate": "lean.extraction",
    "lean_stale_certificate": "lean.extraction",
    "lean_signed_hash_mismatch": "lean.extraction",
}


def main() -> int:
    for case_dir in sorted(GALLERY.iterdir()):
        if not case_dir.is_dir() or case_dir.name.startswith("."):
            continue
        expected_path = case_dir / "expected_failure.json"
        hint_path = case_dir / "repair_hint.json"
        if not expected_path.is_file():
            continue
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        hint_doc = json.loads(hint_path.read_text(encoding="utf-8"))
        artifacts_dir = case_dir / "artifacts"
        artifact_names = sorted(
            p.name for p in artifacts_dir.iterdir() if p.is_file()
        ) if artifacts_dir.is_dir() else []
        case_id = expected["case_id"]
        manifest = {
            "failure_case_id": case_id,
            "workflow_id": WORKFLOW_ID,
            "expected_failure_code": expected["expected_failure_code"],
            "responsible_component": RESPONSIBLE[case_id],
            "artifacts": artifact_names,
            "repair_hint": hint_doc["hint"],
        }
        out = case_dir / "failure_case_manifest.json"
        out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("wrote", out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
