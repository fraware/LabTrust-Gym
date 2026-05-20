"""Unit tests for pcs-bench release_directory path patching."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.benchmark_case import BENCHMARK_CASE_NAME
from labtrust_gym.pcs.benchmark_pcs_bench import (
    PcsBenchCaseRef,
    patch_benchmark_case_release_paths,
    pcs_bench_release_directory,
)


def test_pcs_bench_release_directory_path() -> None:
    ref = PcsBenchCaseRef(
        case_id="labtrust-valid-release-v0",
        polarity="valid",
        path="valid/labtrust-valid-release-v0",
        gallery_case_id="valid_release",
        benchmark_doc={},
    )
    assert (
        pcs_bench_release_directory(
            suite_fixture_root="benchmarks/labtrust-qc-release", case_ref=ref
        )
        == "benchmarks/labtrust-qc-release/valid/labtrust-valid-release-v0/input_artifacts"
    )


def test_patch_benchmark_case_release_paths(tmp_path: Path) -> None:
    case_dir = tmp_path / "valid" / "labtrust-valid-release-v0"
    case_dir.mkdir(parents=True)
    doc = {
        "schema_version": "v0",
        "case_id": "labtrust-valid-release-v0",
        "input_artifacts": {"release_directory": "input_artifacts/"},
    }
    (case_dir / BENCHMARK_CASE_NAME).write_text(json.dumps(doc), encoding="utf-8")
    ref = PcsBenchCaseRef(
        case_id="labtrust-valid-release-v0",
        polarity="valid",
        path="valid/labtrust-valid-release-v0",
        gallery_case_id="valid_release",
        benchmark_doc=doc,
    )
    patch_benchmark_case_release_paths(
        tmp_path, [ref], suite_fixture_root="benchmarks/labtrust-qc-release"
    )
    patched = json.loads((case_dir / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
    assert patched["input_artifacts"]["release_directory"].endswith("/input_artifacts")
