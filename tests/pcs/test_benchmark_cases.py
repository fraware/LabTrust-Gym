"""BenchmarkCase.v0 generation and verification."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from labtrust_gym.pcs.benchmark_case import (
    BENCHMARK_CASE_NAME,
    LABTRUST_EXTENSION_NAME,
    VALID_RELEASE_DIR_NAME,
)
from labtrust_gym.pcs.benchmark_cases import (
    BENCHMARK_INDEX_NAME,
    generate_benchmark_cases,
    verify_benchmark_cases,
)
from labtrust_gym.pcs.bench_schemas import validate_benchmark_case


def test_generate_benchmark_cases_all_thirteen(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    index = generate_benchmark_cases(
        tmp_path / "benchmark",
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
        seed=42,
    )
    assert len(index["cases"]) == 13
    assert index["seed"] == 42
    assert (tmp_path / "benchmark" / VALID_RELEASE_DIR_NAME / BENCHMARK_CASE_NAME).is_file()
    checks = verify_benchmark_cases(tmp_path / "benchmark", policy_root=repo_root)
    assert len(checks) >= 12


def test_benchmark_case_pcs_core_fields_and_extension(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "benchmark"
    generate_benchmark_cases(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
        seed=42,
    )
    doc = json.loads((out / "trace_hash_tamper" / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
    validate_benchmark_case(doc)
    assert doc["workflow_id"] == "hospital_lab.qc_release"
    assert doc["case_kind"] == "invalid_hash_mismatch"
    assert doc["expected_failure_code"] == "trace_hash_mismatch"
    assert doc["expected_responsible_component"] == "runtime_producer"
    assert doc["input_artifacts"]["release_directory"] in ("input_artifacts/", "input_artifacts")
    assert doc["source_repo"].startswith("https://")
    assert len(doc["source_commit"]) == 40
    ext = json.loads(
        (out / "trace_hash_tamper" / LABTRUST_EXTENSION_NAME).read_text(encoding="utf-8")
    )
    assert ext["expected_detection_layer"] == "LabTrust"
    assert ext["expected_protocol_failure_code"] == "STALE_HANDOFF_DIGEST"
    repair = json.loads(
        (out / "trace_hash_tamper" / "expected_repair_hint.json").read_text(encoding="utf-8")
    )
    assert repair["repair_hint"]["kind"] == "regenerate_trace_or_certificate"
    assert (out / "trace_hash_tamper" / "input_artifacts" / "trace.json").is_file()


def test_generate_benchmark_cases_cli(repo_root: Path, release_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "bench_cli"
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
            "--seed",
            "42",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert (out / BENCHMARK_INDEX_NAME).is_file()


def test_benchmark_index_exposes_pcs_bench_layout(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    index = generate_benchmark_cases(
        tmp_path / "benchmark",
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
        seed=42,
    )
    layout = index["pcs_bench"]
    assert layout["case_descriptor"] == BENCHMARK_CASE_NAME
    assert layout["input_dir"] == "input_artifacts"
