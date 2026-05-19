#!/usr/bin/env python3
"""Write proof-obligation hints/identifiers and formalization readiness from release/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.formalization import (
    FORMALIZATION_READINESS_REPORT_NAME,
    PROOF_OBLIGATION_HINTS_NAME,
    PROOF_OBLIGATION_IDENTIFIERS_NAME,
    FormalizationPolicy,
    build_formalization_readiness_report,
    build_proof_obligation_hints,
    collect_proof_obligation_identifiers,
)
from labtrust_gym.pcs.workflow_profile import WorkflowProfileView, resolve_property_id
import json


def _profile_view_without_pcs_validate() -> WorkflowProfileView:
    path = ROOT / "examples" / "pcs_qc_release" / "workflow_profile.v0.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    workflow_id = str(doc["workflow_id"])
    return WorkflowProfileView(
        path=path,
        document=doc,
        workflow_id=workflow_id,
        property_id=resolve_property_id(workflow_id),
        domain=str(doc["domain"]),
        description=str(doc["description"]),
        runtime_artifacts=tuple(doc["runtime_artifacts"]),
        certificate_artifacts=tuple(doc["certificate_artifacts"]),
        handoff_sequence=tuple(doc["handoff_sequence"]),
        required_registry_entries=tuple(doc["required_registry_entries"]),
        failure_modes=tuple(doc["failure_modes"]),
        limitations_notice=str(doc["limitations_notice"]),
        status_policy=dict(doc["status_policy"]),
    )


def main() -> int:
    release = ROOT / "examples" / "pcs_qc_release" / "release"
    profile = _profile_view_without_pcs_validate()
    identifiers = collect_proof_obligation_identifiers(release)
    hints = build_proof_obligation_hints(release, profile=profile)
    report = build_formalization_readiness_report(release, profile=profile)
    paths = []
    for name, doc in (
        (PROOF_OBLIGATION_IDENTIFIERS_NAME, identifiers),
        (PROOF_OBLIGATION_HINTS_NAME, hints),
        (FORMALIZATION_READINESS_REPORT_NAME, report),
    ):
        path = release / name
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(path)
    for path in paths:
        print("wrote", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
