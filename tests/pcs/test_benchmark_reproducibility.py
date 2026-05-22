"""Reproducibility benchmark command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.benchmark_report import BENCHMARK_REPORT_NAME
from labtrust_gym.pcs.benchmark_pcs_bench_ingest import PCS_BENCH_INGEST_NAME
from labtrust_gym.pcs.benchmark_reproducibility import (
    BENCHMARK_MANIFEST_NAME,
    BENCHMARK_RUN_NAME,
    COVERAGE_REPORT_NAME,
    HASH_STABILITY_REPORT_NAME,
    REGENERATION_REPORTS_DIR,
    benchmark_reproducibility,
)
from labtrust_gym.pcs.bench_schemas import (
    validate_benchmark_run,
    validate_hash_stability_report,
    validate_reproducibility_coverage_report,
)


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
        include_hash_stability=False,
    )
    validate_benchmark_run(doc)
    assert doc["aggregate"]["artifact_hashes_stable"] is True
    assert doc["aggregate"]["command_deterministic"] is True
    assert (out / BENCHMARK_RUN_NAME).is_file()
    assert (out / PCS_BENCH_INGEST_NAME).is_file()
    assert (out / BENCHMARK_MANIFEST_NAME).is_file()
    assert (out / BENCHMARK_REPORT_NAME).is_file()
    run_on_disk = json.loads((out / BENCHMARK_RUN_NAME).read_text(encoding="utf-8"))
    assert run_on_disk.get("signature_or_digest", "").startswith("sha256:")
    coverage = json.loads((out / COVERAGE_REPORT_NAME).read_text(encoding="utf-8"))
    validate_reproducibility_coverage_report(coverage)
    assert coverage["reproducibility_passed"] is True


@pytest.mark.slow
@pytest.mark.timeout(900)
def test_benchmark_reproducibility_release_grade(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "repro_full"
    try:
        doc = benchmark_reproducibility(
            out,
            workflow_key="hospital_lab.qc_release",
            policy_root=repo_root,
            release_dir=release_dir,
            runs=5,
            seed=42,
            mode="full_regeneration",
        )
    except Exception as exc:
        from labtrust_gym.pcs.benchmark_reproducibility import RegenerationUnavailableError

        if not isinstance(exc, RegenerationUnavailableError):
            raise
        pytest.skip(f"full_regeneration unavailable: {exc}")

    validate_benchmark_run(doc)
    assert (out / BENCHMARK_RUN_NAME).is_file()
    assert (out / HASH_STABILITY_REPORT_NAME).is_file()
    assert (out / REGENERATION_REPORTS_DIR).is_dir()
    assert any((out / REGENERATION_REPORTS_DIR).glob("run_*_regeneration_report.json"))

    hash_doc = json.loads((out / HASH_STABILITY_REPORT_NAME).read_text(encoding="utf-8"))
    validate_hash_stability_report(hash_doc)
    coverage = json.loads((out / COVERAGE_REPORT_NAME).read_text(encoding="utf-8"))
    validate_reproducibility_coverage_report(coverage)
    assert "hash_stability_passed" in coverage
