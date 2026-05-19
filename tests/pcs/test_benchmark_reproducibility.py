"""Reproducibility benchmark command."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.benchmark_reproducibility import (
    BENCHMARK_RUN_NAME,
    COVERAGE_REPORT_NAME,
    benchmark_reproducibility,
)
from labtrust_gym.pcs.bench_schemas import validate_benchmark_run, validate_reproducibility_coverage_report


def test_benchmark_reproducibility_hash_stability(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "repro"
    doc = benchmark_reproducibility(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
        runs=3,
        seed=42,
        mode="hash_stability",
    )
    validate_benchmark_run(doc)
    assert doc["aggregate"]["artifact_hashes_stable"] is True
    assert doc["aggregate"]["command_deterministic"] is True
    assert (out / BENCHMARK_RUN_NAME).is_file()
    coverage = json.loads((out / COVERAGE_REPORT_NAME).read_text(encoding="utf-8"))
    validate_reproducibility_coverage_report(coverage)
    assert coverage["reproducibility_passed"] is True
