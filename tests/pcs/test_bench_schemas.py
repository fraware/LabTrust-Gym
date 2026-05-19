"""JSON Schema contracts for pcs-bench artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.bench_schemas import (
    validate_failure_case_manifest,
    validate_formalization_readiness_report,
    validate_proof_obligation_hints,
    validate_proof_obligation_identifiers,
    validate_regeneration_report_doc,
)
from labtrust_gym.pcs.formalization import (
    FORMALIZATION_READINESS_REPORT_NAME,
    PROOF_OBLIGATION_HINTS_NAME,
    PROOF_OBLIGATION_IDENTIFIERS_NAME,
)
from labtrust_gym.pcs.regeneration_report import REGENERATION_REPORT_NAME
from labtrust_gym.policy.loader import PolicyLoadError


def test_committed_regeneration_report_validates_against_schema(release_dir: Path) -> None:
    doc = json.loads((release_dir / REGENERATION_REPORT_NAME).read_text(encoding="utf-8"))
    validate_regeneration_report_doc(doc)


def test_committed_failure_manifest_validates_against_schema(repo_root: Path) -> None:
    manifest = (
        repo_root
        / "examples/pcs_qc_release/failures/missing_qc_result/failure_case_manifest.json"
    )
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    validate_failure_case_manifest(doc)


def test_committed_formalization_artifacts_validate(release_dir: Path) -> None:
    hints = json.loads((release_dir / PROOF_OBLIGATION_HINTS_NAME).read_text(encoding="utf-8"))
    ids_doc = json.loads(
        (release_dir / PROOF_OBLIGATION_IDENTIFIERS_NAME).read_text(encoding="utf-8")
    )
    report = json.loads(
        (release_dir / FORMALIZATION_READINESS_REPORT_NAME).read_text(encoding="utf-8")
    )
    validate_proof_obligation_hints(hints)
    validate_proof_obligation_identifiers(ids_doc)
    validate_formalization_readiness_report(report)


def test_regeneration_report_schema_rejects_invalid_status(repo_root: Path) -> None:
    doc = {
        "workflow_id": "x",
        "artifacts_written": [],
        "artifact_hashes": {},
        "handoffs_written": [],
        "certificate_id": None,
        "trace_hash": None,
        "certified_bundle_hash": None,
        "duration_ms": 0,
        "status": "bogus",
        "failure_code": None,
    }
    with pytest.raises(PolicyLoadError):
        validate_regeneration_report_doc(doc, policy_root=repo_root)
