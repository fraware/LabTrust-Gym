"""JSON Schema contracts for pcs-bench artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.bench_schemas import (
    validate_benchmark_artifact_ref,
    validate_benchmark_case,
    validate_coverage_report,
    validate_failure_case_manifest,
    validate_formalization_readiness_report,
    validate_proof_obligation_hints,
    validate_proof_obligation_identifiers,
    validate_regeneration_report_doc,
    validate_reproducibility_benchmark_manifest,
    validate_reproducibility_coverage_report,
)
from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    EVIDENCE_GRADE_RELEASE,
    build_reproducibility_benchmark_manifest,
)
from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID
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


def test_committed_benchmark_coverage_report(repo_root: Path) -> None:
    path = repo_root / "examples/pcs_qc_release/benchmark/coverage_report.v0.json"
    if not path.is_file():
        return
    validate_coverage_report(json.loads(path.read_text(encoding="utf-8")))


def test_reproducibility_benchmark_manifest_release_fields(repo_root: Path) -> None:
    manifest = build_reproducibility_benchmark_manifest(
        workflow_id=CANONICAL_QC_RELEASE_WORKFLOW_ID,
        mode="full_regeneration",
        runs=2,
        policy_root=repo_root,
        evidence_grade=EVIDENCE_GRADE_RELEASE,
        certifyedge_live=True,
        pcs_core_validation=True,
    )
    validate_reproducibility_benchmark_manifest(manifest, policy_root=repo_root)
    assert manifest["evidence_grade"] == EVIDENCE_GRADE_RELEASE
    assert manifest["certifyedge_live"] is True
    assert manifest["pcs_core_validation"] is True


def test_benchmark_artifact_ref_schema(repo_root: Path) -> None:
    ref = {
        "schema_version": "v0",
        "artifact_type": "BenchmarkRun.v0",
        "path": "benchmark_run.v0.json",
        "sha256": "sha256:" + "a" * 64,
        "role": "reproducibility_evidence",
        "source_repo": "https://github.com/example/repo",
        "source_commit": "0000000000000000000000000000000000000001",
        "signature_or_digest": "sha256:" + "b" * 64,
    }
    validate_benchmark_artifact_ref(ref, policy_root=repo_root)


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
