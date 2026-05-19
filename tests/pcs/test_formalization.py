"""Proof-obligation readiness and Lean boundary checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.formalization import (
    FORMALIZATION_READINESS_REPORT_NAME,
    PROOF_OBLIGATION_HINTS_NAME,
    PROOF_OBLIGATION_IDENTIFIERS_NAME,
    build_formalization_readiness_report,
    build_proof_obligation_hints,
    check_certificate_matches_runtime,
    check_certificate_status_allowed,
    check_verification_admits_bundle,
    run_lean_obligation_check,
    write_formalization_artifacts,
)
from labtrust_gym.pcs.failure_gallery import build_single_failure_case, demonstrate_case_failure
from labtrust_gym.pcs.workflow_profile import assert_workflow_profile_valid, load_workflow_profile


def test_workflow_profile_has_trust_envelope_formalization(repo_root: Path) -> None:
    doc = load_workflow_profile(
        repo_root / "examples/pcs_qc_release/workflow_profile.v0.json",
        policy_root=repo_root,
    )
    assert_workflow_profile_valid(doc)
    block = doc["formalization"]
    assert block["formalization_scope"] == "trust_envelope_only"
    assert "CertificateMatchesRuntime" in block["required_obligations"]


def test_write_formalization_artifacts(release_dir: Path, repo_root: Path) -> None:
    paths = write_formalization_artifacts(release_dir, policy_root=repo_root)
    names = {p.name for p in paths}
    assert PROOF_OBLIGATION_HINTS_NAME in names
    assert PROOF_OBLIGATION_IDENTIFIERS_NAME in names
    assert FORMALIZATION_READINESS_REPORT_NAME in names
    hints = json.loads((release_dir / PROOF_OBLIGATION_HINTS_NAME).read_text(encoding="utf-8"))
    assert hints["workflow_id"] == "hospital_lab.qc_release"
    assert hints["claim_id"] == "claim-pcs-qc-release-v0.1"


def test_lean_trace_hash_mismatch_case(repo_root: Path, release_dir: Path, tmp_path: Path) -> None:
    case_dir = tmp_path / "lean_trace_hash_mismatch"
    build_single_failure_case(
        "lean_trace_hash_mismatch",
        case_dir,
        policy_root=repo_root,
        release_dir=release_dir,
    )
    label = demonstrate_case_failure(case_dir, policy_root=repo_root)
    assert label == "lean_obligation.CertificateMatchesRuntime"


@pytest.mark.parametrize(
    "case_id",
    [
        "lean_rejected_certificate",
        "lean_stale_certificate",
    ],
)
def test_lean_certificate_status_cases(
    repo_root: Path, release_dir: Path, tmp_path: Path, case_id: str
) -> None:
    case_dir = tmp_path / case_id
    build_single_failure_case(case_id, case_dir, policy_root=repo_root, release_dir=release_dir)
    label = demonstrate_case_failure(case_dir, policy_root=repo_root)
    assert label == "lean_obligation.CertificateMatchesRuntime"


def test_lean_signed_hash_mismatch_case(repo_root: Path, release_dir: Path, tmp_path: Path) -> None:
    case_dir = tmp_path / "lean_signed_hash_mismatch"
    build_single_failure_case(
        "lean_signed_hash_mismatch",
        case_dir,
        policy_root=repo_root,
        release_dir=release_dir,
    )
    label = demonstrate_case_failure(case_dir, policy_root=repo_root)
    assert label == "lean_obligation.VerificationAdmitsBundle"


def test_release_passes_certificate_matches_runtime(release_dir: Path) -> None:
    check_certificate_matches_runtime(release_dir)
    check_certificate_status_allowed(release_dir)


def test_formalization_readiness_report_shape(release_dir: Path, repo_root: Path) -> None:
    report = build_formalization_readiness_report(release_dir, policy_root=repo_root)
    assert report["formalization_scope"] == "trust_envelope_only"
    assert set(report) >= {
        "workflow_id",
        "formalization_scope",
        "required_obligations",
        "all_required_inputs_present",
        "missing_inputs",
        "status",
    }


def test_run_lean_obligation_on_release(release_dir: Path) -> None:
    run_lean_obligation_check("CertificateMatchesRuntime", release_dir)
