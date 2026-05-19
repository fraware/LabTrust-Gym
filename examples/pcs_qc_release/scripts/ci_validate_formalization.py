#!/usr/bin/env python3
"""CI: validate proof-obligation hints and formalization readiness report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.formalization import (
    FORMALIZATION_READINESS_REPORT_NAME,
    PROOF_OBLIGATION_HINTS_NAME,
    PROOF_OBLIGATION_IDENTIFIERS_NAME,
    assert_formalization_block_valid,
    build_formalization_readiness_report,
    build_proof_obligation_hints,
    collect_proof_obligation_identifiers,
)
from labtrust_gym.pcs.workflow_profile import load_workflow_profile, workflow_profile_view

RELEASE = ROOT / "examples" / "pcs_qc_release" / "release"
PROFILE = ROOT / "examples" / "pcs_qc_release" / "workflow_profile.v0.json"


def main() -> int:
    profile_doc = load_workflow_profile(PROFILE, policy_root=ROOT)
    assert_formalization_block_valid(profile_doc["formalization"])
    profile = workflow_profile_view(PROFILE, policy_root=ROOT)

    hints_path = RELEASE / PROOF_OBLIGATION_HINTS_NAME
    ids_path = RELEASE / PROOF_OBLIGATION_IDENTIFIERS_NAME
    report_path = RELEASE / FORMALIZATION_READINESS_REPORT_NAME
    for path in (hints_path, ids_path, report_path):
        if not path.is_file():
            raise FileNotFoundError(f"missing {path.relative_to(ROOT)}")

    hints = json.loads(hints_path.read_text(encoding="utf-8"))
    expected_hints = build_proof_obligation_hints(RELEASE, profile=profile, policy_root=ROOT)
    for key in (
        "workflow_id",
        "claim_id",
        "runtime_receipt",
        "trace_certificate",
        "certified_bundle",
        "required_obligations",
    ):
        if hints.get(key) != expected_hints.get(key):
            raise ValueError(f"proof_obligation_hints.{key} mismatch")

    ids = json.loads(ids_path.read_text(encoding="utf-8"))
    expected_ids = collect_proof_obligation_identifiers(RELEASE)
    for key in (
        "runtime_receipt_id",
        "trace_hash",
        "certificate_id",
        "certificate_trace_hash",
        "certified_bundle_hash",
        "workflow_id",
        "claim_id",
    ):
        if ids.get(key) != expected_ids.get(key):
            raise ValueError(f"proof_obligation_identifiers.{key} mismatch")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("formalization_scope") != "trust_envelope_only":
        raise ValueError("formalization_scope must be trust_envelope_only")
    if report.get("status") != "passed":
        raise ValueError(f"expected status passed, got {report.get('status')!r}")
    if not report.get("all_required_inputs_present"):
        raise ValueError("all_required_inputs_present must be true for reference release")

    print("OK", PROOF_OBLIGATION_HINTS_NAME)
    print("OK", PROOF_OBLIGATION_IDENTIFIERS_NAME)
    print("OK", FORMALIZATION_READINESS_REPORT_NAME)
    print("formalization CI OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
