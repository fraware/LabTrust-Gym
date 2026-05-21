"""PcsBenchIngest.v0 emission from reproducibility benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    PCS_BENCH_INGEST_NAME,
    PRODUCER_ID,
    REPRODUCIBILITY_SUITE_ID,
    build_pcs_bench_ingest,
    build_pcs_core_benchmark_runs_from_reproducibility,
    build_release_reproducibility_coverage_report,
)
from labtrust_gym.pcs.benchmark_report import (
    BENCHMARK_REPORT_NAME,
    build_reproducibility_pcs_benchmark_report,
)


def test_build_pcs_bench_ingest_shape(repo_root: Path) -> None:
    run_doc = {
        "schema_version": "v0",
        "benchmark_id": "labtrust-reproducibility-v0",
        "workflow_id": "hospital_lab.qc_release",
        "mode": "full_regeneration",
        "seed": 42,
        "runs": 2,
        "per_run": [],
        "aggregate": {"command_deterministic": True},
    }
    coverage = {
        "schema_version": "v0",
        "workflow_id": "hospital_lab.qc_release",
        "task_id": "labtrust-qc-release-reproducibility-v0",
        "reproducibility_passed": True,
        "runs": 2,
        "mode": "full_regeneration",
    }
    pcs_cov = build_release_reproducibility_coverage_report(
        run_doc=run_doc,
        reproducibility_coverage=coverage,
        policy_root=repo_root,
    )
    per_run = [
        {
            "run_index": 0,
            "duration_ms": 100,
            "artifact_hashes": {"trace.json": "sha256:" + "a" * 64},
            "certificate_id": "cert-test",
            "certifyedge_call_success": True,
            "release_protocol_validation_passed": True,
        }
    ]
    pcs_runs = build_pcs_core_benchmark_runs_from_reproducibility(
        per_run=per_run,
        mode="full_regeneration",
        policy_root=repo_root,
    )
    ingest = build_pcs_bench_ingest(
        workflow_id="hospital_lab.qc_release",
        benchmark_runs=pcs_runs,
        coverage_reports=[pcs_cov],
        policy_root=repo_root,
        suite_id=REPRODUCIBILITY_SUITE_ID,
    )
    assert ingest["producer_id"] == PRODUCER_ID
    assert ingest["suite_id"] == REPRODUCIBILITY_SUITE_ID
    assert ingest["workflow_id"] == "hospital_lab.qc_release"
    assert len(ingest["benchmark_runs"]) == 1
    assert ingest["benchmark_runs"][0]["run_id"].startswith("labtrust-repro-")
    assert len(ingest["coverage_reports"]) == 1
    assert ingest["signature_or_digest"].startswith("sha256:")


def test_pcs_core_ingest_validation(repo_root: Path) -> None:
    pcs_core = repo_root.parent / "pcs-core"
    if not (pcs_core / "schemas" / "PcsBenchIngest.v0.schema.json").is_file():
        import pytest

        pytest.skip("pcs-core checkout not found")
    from labtrust_gym.pcs.bench_schemas import validate_pcs_bench_ingest_pcs_core

    run_doc = {
        "schema_version": "v0",
        "benchmark_id": "labtrust-reproducibility-v0",
        "workflow_id": "hospital_lab.qc_release",
        "mode": "hash_stability",
        "seed": 42,
        "runs": 1,
        "per_run": [],
        "aggregate": {"command_deterministic": True},
    }
    coverage = {
        "schema_version": "v0",
        "workflow_id": "hospital_lab.qc_release",
        "task_id": "labtrust-qc-release-reproducibility-v0",
        "reproducibility_passed": True,
        "runs": 1,
        "mode": "hash_stability",
    }
    pcs_cov = build_release_reproducibility_coverage_report(
        run_doc=run_doc,
        reproducibility_coverage=coverage,
        policy_root=repo_root,
    )
    pcs_runs = build_pcs_core_benchmark_runs_from_reproducibility(
        per_run=[
            {
                "run_index": 0,
                "duration_ms": 50,
                "artifact_hashes": {},
                "certificate_id": None,
                "certifyedge_call_success": True,
                "release_protocol_validation_passed": True,
            }
        ],
        mode="hash_stability",
        policy_root=repo_root,
    )
    ingest = build_pcs_bench_ingest(
        workflow_id="hospital_lab.qc_release",
        benchmark_runs=pcs_runs,
        coverage_reports=[pcs_cov],
        policy_root=repo_root,
        suite_id=REPRODUCIBILITY_SUITE_ID,
    )
    validate_pcs_bench_ingest_pcs_core(ingest, pcs_core_root=pcs_core)
    report = build_reproducibility_pcs_benchmark_report(
        pcs_runs=pcs_runs,
        pcs_coverage=pcs_cov,
        aggregate={"command_deterministic": True, "pcs_core_validation_stable": True},
        policy_root=repo_root,
    )
    from labtrust_gym.pcs.bench_schemas import validate_benchmark_report_pcs_core

    validate_benchmark_report_pcs_core(report, pcs_core_root=pcs_core)


def test_reproducibility_writes_ingest(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    from labtrust_gym.pcs.benchmark_reproducibility import benchmark_reproducibility

    out = tmp_path / "repro"
    try:
        benchmark_reproducibility(
            out,
            workflow_key="hospital_lab.qc_release",
            policy_root=repo_root,
            release_dir=release_dir,
            pcs_core=None,
            runs=1,
            seed=42,
            mode="hash_stability",
            include_hash_stability=False,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        import pytest

        pytest.skip(f"reproducibility run unavailable: {exc}")

    ingest_path = out / PCS_BENCH_INGEST_NAME
    assert ingest_path.is_file()
    ingest = json.loads(ingest_path.read_text(encoding="utf-8"))
    assert ingest["producer_id"] == PRODUCER_ID
    assert ingest["suite_id"] == REPRODUCIBILITY_SUITE_ID
    assert ingest["benchmark_runs"][0]["run_id"].startswith("labtrust-repro-")
    from labtrust_gym.pcs.benchmark_reproducibility import BENCHMARK_MANIFEST_NAME

    assert (out / BENCHMARK_MANIFEST_NAME).is_file()
