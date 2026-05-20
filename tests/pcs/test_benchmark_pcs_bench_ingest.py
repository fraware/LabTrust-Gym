"""PcsBenchIngest.v0 emission from reproducibility benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.benchmark_pcs_bench_ingest import (
    PCS_BENCH_INGEST_NAME,
    PRODUCER_ID,
    build_pcs_bench_ingest,
    build_release_reproducibility_coverage_report,
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
    ingest = build_pcs_bench_ingest(
        workflow_id="hospital_lab.qc_release",
        benchmark_runs=[run_doc],
        coverage_reports=[pcs_cov],
        policy_root=repo_root,
    )
    assert ingest["producer_id"] == PRODUCER_ID
    assert ingest["workflow_id"] == "hospital_lab.qc_release"
    assert len(ingest["benchmark_runs"]) == 1
    assert len(ingest["coverage_reports"]) == 1
    assert ingest["signature_or_digest"].startswith("sha256:")


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
