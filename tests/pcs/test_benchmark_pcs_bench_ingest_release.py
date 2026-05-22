"""Release-grade manifest, gates, and sidecar artifact refs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    EVIDENCE_GRADE_DEVELOPER,
    EVIDENCE_GRADE_RELEASE,
    build_reproducibility_benchmark_manifest,
    build_reproducibility_sidecar_artifact_refs,
    enforce_release_grade_gate,
    release_grade_flags,
)
from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID


def _per_run(*, pcs_ok: bool = True, release_ok: bool = True, status_ok: bool = True) -> list[dict]:
    return [
        {
            "run_index": 0,
            "duration_ms": 10,
            "artifact_hashes": {},
            "certifyedge_call_success": True,
            "release_protocol_validation_passed": release_ok,
            "status_policy_validation_passed": status_ok,
            "pcs_core_validation_passed": pcs_ok,
        }
    ]


def test_producer_ingest_contract_rejects_noncanonical_workflow(repo_root: Path) -> None:
    from labtrust_gym.pcs.bench_schemas import validate_producer_ingest_contract
    from labtrust_gym.policy.loader import PolicyLoadError

    bad = {
        "schema_version": "v0",
        "producer_id": "labtrust-gym",
        "suite_id": "x",
        "workflow_id": "qc-release",
        "benchmark_runs": [{}],
        "coverage_reports": [{}],
        "failure_localization_reports": [],
        "explain_quality_reports": [],
        "profile_coverage_reports": [],
        "commands": [],
        "logs": [],
        "artifact_refs": [
            {
                "schema_version": "v0",
                "artifact_type": "BenchmarkRun.v0",
                "path": "a.json",
                "sha256": "sha256:" + "a" * 64,
                "role": "producer_export",
                "source_repo": "https://example.com",
                "source_commit": "0000000000000000000000000000000000000001",
                "signature_or_digest": "sha256:" + "b" * 64,
            }
        ]
        * 4,
        "source_repo": "https://example.com",
        "source_commit": "0000000000000000000000000000000000000001",
        "signature_or_digest": "sha256:" + "c" * 64,
    }
    with pytest.raises(PolicyLoadError, match="workflow_id"):
        validate_producer_ingest_contract(bad, policy_root=repo_root)


def test_collect_release_metrics_skips_canonical_byte_compare(repo_root: Path) -> None:
    from labtrust_gym.pcs.benchmark_reproducibility import _collect_release_metrics
    from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol

    release = repo_root / "examples" / "pcs_qc_release" / "release"
    pcs_core = repo_root.parent / "pcs-core"
    if not (pcs_core / "schemas").is_dir():
        import pytest

        pytest.skip("pcs-core not found")
    checks = verify_release_protocol(
        release,
        pcs_core=pcs_core,
        policy_root=repo_root,
        compare_canonical=False,
    )
    assert any(c.startswith("schema_validate") for c in checks)
    metrics = _collect_release_metrics(
        release,
        pcs_core=pcs_core,
        policy_root=repo_root,
        certifyedge_call_success=True,
    )
    assert metrics["release_protocol_validation_passed"] is True
    assert metrics["pcs_core_validation_passed"] is True


def test_enforce_release_grade_requires_full_regeneration() -> None:
    with pytest.raises(ValueError, match="full_regeneration"):
        enforce_release_grade_gate(
            mode="hash_stability",
            per_run=_per_run(),
            aggregate={"certifyedge_success_rate": 1.0},
        )


def test_enforce_release_grade_requires_certifyedge_success() -> None:
    with pytest.raises(ValueError, match="certifyedge"):
        enforce_release_grade_gate(
            mode="full_regeneration",
            per_run=_per_run(),
            aggregate={"certifyedge_success_rate": 0.5},
        )


def test_enforce_release_grade_requires_per_run_validation() -> None:
    with pytest.raises(ValueError, match="pcs_core_validation_passed"):
        enforce_release_grade_gate(
            mode="full_regeneration",
            per_run=_per_run(pcs_ok=False),
            aggregate={"certifyedge_success_rate": 1.0},
        )


def test_release_manifest_fields(repo_root: Path) -> None:
    manifest = build_reproducibility_benchmark_manifest(
        workflow_id=CANONICAL_QC_RELEASE_WORKFLOW_ID,
        mode="full_regeneration",
        runs=3,
        policy_root=repo_root,
        evidence_grade=EVIDENCE_GRADE_RELEASE,
        certifyedge_live=True,
        pcs_core_validation=True,
    )
    assert manifest["evidence_grade"] == EVIDENCE_GRADE_RELEASE
    assert manifest["mode"] == "full_regeneration"
    assert manifest["certifyedge_live"] is True
    assert manifest["pcs_core_validation"] is True
    assert manifest["workflow_id"] == CANONICAL_QC_RELEASE_WORKFLOW_ID


def test_developer_manifest_defaults(repo_root: Path) -> None:
    manifest = build_reproducibility_benchmark_manifest(
        workflow_id=CANONICAL_QC_RELEASE_WORKFLOW_ID,
        mode="hash_stability",
        runs=1,
        policy_root=repo_root,
        evidence_grade=EVIDENCE_GRADE_DEVELOPER,
        certifyedge_live=False,
        pcs_core_validation=False,
    )
    assert manifest["evidence_grade"] == EVIDENCE_GRADE_DEVELOPER
    assert manifest["certifyedge_live"] is False


def test_release_grade_flags_full_regeneration() -> None:
    live, pcs_val = release_grade_flags(
        mode="full_regeneration",
        per_run=_per_run(),
        aggregate={"certifyedge_success_rate": 1.0},
        pcs_core_configured=True,
    )
    assert live is True
    assert pcs_val is True


def test_sidecar_artifact_refs_roles(repo_root: Path, tmp_path: Path) -> None:
    run_doc = {
        "schema_version": "v0",
        "benchmark_id": "x",
        "workflow_id": CANONICAL_QC_RELEASE_WORKFLOW_ID,
        "signature_or_digest": "sha256:" + "c" * 64,
    }
    coverage = {"schema_version": "v0", "signature_or_digest": "sha256:" + "d" * 64}
    report = {"schema_version": "v0", "signature_or_digest": "sha256:" + "e" * 64}
    manifest = build_reproducibility_benchmark_manifest(
        workflow_id=CANONICAL_QC_RELEASE_WORKFLOW_ID,
        mode="hash_stability",
        runs=1,
        policy_root=repo_root,
        evidence_grade=EVIDENCE_GRADE_DEVELOPER,
    )
    (tmp_path / "hash_stability_report.v0.json").write_text(
        json.dumps({"schema_version": "v0", "signature_or_digest": "sha256:" + "f" * 64}),
        encoding="utf-8",
    )
    regen_dir = tmp_path / "regeneration_reports"
    regen_dir.mkdir()
    (regen_dir / "run_0_regeneration_report.json").write_text(
        json.dumps({"schema_version": "v0", "signature_or_digest": "sha256:" + "0" * 64}),
        encoding="utf-8",
    )
    refs = build_reproducibility_sidecar_artifact_refs(
        out_dir=tmp_path,
        run_doc=run_doc,
        pcs_coverage=coverage,
        benchmark_report=report,
        benchmark_manifest=manifest,
        source_repo="https://example.com/repo",
        source_commit="0000000000000000000000000000000000000001",
    )
    roles = {r["role"] for r in refs}
    types = {r["artifact_type"] for r in refs}
    assert "native_report" in roles
    assert "reproducibility_evidence" in roles
    assert "regeneration_report" in roles
    assert "BenchmarkReport.v0" in types
    assert "HashStabilityReport.v0" in types
    assert "RegenerationReport.v0" in types
    assert len(refs) >= 4


def test_pcs_core_ingest_refs_match_embedded_runs(repo_root: Path, tmp_path: Path) -> None:
    from labtrust_gym.pcs.benchmark_pcs_bench_ingest import build_pcs_core_reproducibility_artifact_refs

    run = {
        "schema_version": "v0",
        "run_id": "labtrust-repro-hash_stability-run-0",
        "task_id": "t",
        "case_id": "c",
        "started_at": "2026-05-16T12:00:00Z",
        "completed_at": "2026-05-16T12:00:01Z",
        "commands": [],
        "artifacts_produced": [],
        "observed_status": "passed",
        "release_chain_status": "valid",
        "certificate_status": "CertificateChecked",
        "duration_ms": 1,
        "source_repo": "https://example.com/r",
        "source_commit": "0000000000000000000000000000000000000001",
        "signature_or_digest": "sha256:" + "a" * 64,
    }
    cov = {
        "schema_version": "v0",
        "coverage_id": "cov-1",
        "metric": "release_reproducibility_score",
        "metric_id": "release_reproducibility_score",
        "numerator": 1.0,
        "denominator": 1.0,
        "coverage_ratio": 1.0,
        "details": {},
        "source_repo": "https://example.com/r",
        "source_commit": "0000000000000000000000000000000000000001",
        "signature_or_digest": "sha256:" + "b" * 64,
    }
    refs = build_pcs_core_reproducibility_artifact_refs(
        out_dir=tmp_path,
        pcs_runs=[run],
        pcs_coverage=cov,
        source_repo="https://example.com/r",
        source_commit="0000000000000000000000000000000000000001",
    )
    assert len(refs) == 2
    assert all(r["role"] == "producer_export" for r in refs)
    assert (tmp_path / "artifact_refs/benchmark_runs/labtrust-repro-hash_stability-run-0.v0.json").is_file()


def test_reproducibility_uses_canonical_workflow_from_alias(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    from labtrust_gym.pcs.benchmark_reproducibility import (
        BENCHMARK_MANIFEST_NAME,
        PCS_BENCH_INGEST_NAME,
        benchmark_reproducibility,
    )

    out = tmp_path / "alias"
    doc = benchmark_reproducibility(
        out,
        workflow_key="qc-release",
        policy_root=repo_root,
        release_dir=release_dir,
        runs=1,
        seed=1,
        mode="hash_stability",
        include_hash_stability=False,
        release_grade=False,
    )
    assert doc["workflow_id"] == CANONICAL_QC_RELEASE_WORKFLOW_ID
    ingest = json.loads((out / PCS_BENCH_INGEST_NAME).read_text(encoding="utf-8"))
    manifest = json.loads((out / BENCHMARK_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert ingest["workflow_id"] == CANONICAL_QC_RELEASE_WORKFLOW_ID
    assert manifest["workflow_id"] == CANONICAL_QC_RELEASE_WORKFLOW_ID
    assert manifest["evidence_grade"] == EVIDENCE_GRADE_DEVELOPER
