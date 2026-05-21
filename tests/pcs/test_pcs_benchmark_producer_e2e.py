"""End-to-end PCS benchmark producer validation (cases + reproducibility ingest)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.bench_schemas import (
    resolve_pcs_core_schema_root,
    validate_pcs_core_benchmark_suite_outputs,
    validate_pcs_core_reproducibility_outputs,
)
from labtrust_gym.pcs.benchmark_pcs_bench import PCS_BENCH_SUITE_ID, generate_benchmark_cases_pcs_bench
from labtrust_gym.pcs.benchmark_pcs_bench_ingest import PCS_BENCH_INGEST_NAME
from labtrust_gym.pcs.benchmark_reproducibility import benchmark_reproducibility


@pytest.fixture
def pcs_core_root(repo_root: Path) -> Path | None:
    return resolve_pcs_core_schema_root(repo_root.parent / "pcs-core")


def test_pcs_bench_suite_pcs_core_validation(
    repo_root: Path, release_dir: Path, tmp_path: Path, pcs_core_root: Path | None
) -> None:
    if pcs_core_root is None:
        pytest.skip("pcs-core checkout not found")
    out = tmp_path / "suite"
    generate_benchmark_cases_pcs_bench(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
        seed=42,
        suite_id=PCS_BENCH_SUITE_ID,
        suite_fixture_root="benchmarks/labtrust-qc-release",
        validate_pcs_core_output=pcs_core_root,
    )
    checks = validate_pcs_core_benchmark_suite_outputs(
        out, pcs_core_root=pcs_core_root, policy_root=repo_root
    )
    assert "benchmark_task.pcs_core" in checks
    assert any("benchmark_case" in c for c in checks)


def test_reproducibility_ingest_pcs_core_validation(
    repo_root: Path, release_dir: Path, tmp_path: Path, pcs_core_root: Path | None
) -> None:
    if pcs_core_root is None:
        pytest.skip("pcs-core checkout not found")
    out = tmp_path / "repro"
    benchmark_reproducibility(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
        pcs_core=pcs_core_root,
        runs=2,
        seed=42,
        mode="hash_stability",
        include_hash_stability=False,
        validate_pcs_core_output=pcs_core_root,
    )
    checks = validate_pcs_core_reproducibility_outputs(
        out, pcs_core_root=pcs_core_root, policy_root=repo_root
    )
    assert "pcs_bench_ingest.pcs_core" in checks
    assert "benchmark_report.pcs_core" in checks
    ingest = json.loads((out / PCS_BENCH_INGEST_NAME).read_text(encoding="utf-8"))
    assert len(ingest["benchmark_runs"]) == 2
    assert ingest["benchmark_runs"][0]["run_id"].startswith("labtrust-repro-")
