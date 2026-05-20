"""pcs-bench layout generation and manifest."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from labtrust_gym.pcs.benchmark_case import BENCHMARK_CASE_NAME, PCS_BENCH_RELEASE_DIRECTORY
from labtrust_gym.pcs.benchmark_cases import verify_benchmark_cases
from labtrust_gym.pcs.benchmark_pcs_bench import (
    BENCHMARK_MANIFEST_NAME,
    SUITE_YAML_NAME,
    generate_benchmark_cases_pcs_bench,
    is_pcs_bench_layout,
)
from labtrust_gym.pcs.bench_schemas import validate_benchmark_manifest


def test_generate_pcs_bench_layout(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "suite"
    result = generate_benchmark_cases_pcs_bench(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
        seed=42,
        suite_fixture_root="benchmarks/labtrust-qc-release-test",
    )
    assert is_pcs_bench_layout(out)
    assert (out / SUITE_YAML_NAME).is_file()
    assert (out / BENCHMARK_MANIFEST_NAME).is_file()
    assert (out / "coverage_report.v0.json").is_file()
    assert result["valid_cases"] == ["labtrust-valid-release-v0"]
    assert len(result["invalid_cases"]) == 12

    suite = yaml.safe_load((out / SUITE_YAML_NAME).read_text(encoding="utf-8"))
    assert set(suite["valid_cases"]) == set(result["valid_cases"])
    assert set(suite["invalid_cases"]) == set(result["invalid_cases"])

    manifest = json.loads((out / BENCHMARK_MANIFEST_NAME).read_text(encoding="utf-8"))
    validate_benchmark_manifest(manifest)
    assert manifest["generator"] == "labtrust"
    assert len(manifest["source_commit"]) == 40
    assert manifest["case_count"] == 13
    assert len(manifest["case_ids"]) == 13

    valid_doc = json.loads(
        (out / "valid" / "labtrust-valid-release-v0" / BENCHMARK_CASE_NAME).read_text(
            encoding="utf-8"
        )
    )
    assert valid_doc["input_artifacts"]["release_directory"].endswith("/input_artifacts")
    assert valid_doc["expected_system_outcome"] == "admitted"
    assert valid_doc["expected_failure_code"] is None
    assert (out / "benchmark_task.v0.json").is_file()
    assert not (out / "valid" / "labtrust-valid-release-v0" / "expected_failure.json").is_file()

    checks = verify_benchmark_cases(out, policy_root=repo_root)
    assert len(checks) >= 13


def test_cli_pcs_bench_layout_flag(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    import subprocess
    import sys

    out = tmp_path / "cli_suite"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "generate-benchmark-cases",
            "--workflow",
            "hospital_lab.qc_release",
            "--out",
            str(out),
            "--release-dir",
            str(release_dir),
            "--pcs-bench-layout",
            "--seed",
            "42",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert (out / SUITE_YAML_NAME).is_file()
