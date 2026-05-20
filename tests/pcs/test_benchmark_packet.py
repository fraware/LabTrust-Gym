"""Committed benchmark_packet smoke fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.benchmark_case import BENCHMARK_CASE_NAME, LABTRUST_EXTENSION_NAME
from labtrust_gym.pcs.benchmark_cases import verify_benchmark_cases
from labtrust_gym.pcs.bench_schemas import validate_benchmark_case

PACKET_ROOT = Path("examples/pcs_qc_release/benchmark_packet")


def test_benchmark_packet_cases_validate(repo_root: Path) -> None:
    root = repo_root / PACKET_ROOT
    if not (root / "valid_release" / BENCHMARK_CASE_NAME).is_file():
        return
    for case_id in ("valid_release", "invalid_trace_hash_tamper"):
        doc = json.loads((root / case_id / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
        validate_benchmark_case(doc, policy_root=repo_root)
        assert (root / case_id / LABTRUST_EXTENSION_NAME).is_file()
    expected = json.loads((root / "expected_report.json").read_text(encoding="utf-8"))
    assert expected["benchmark_suite_id"] == "labtrust-qc-release-v0"
    assert len(expected["cases"]) == 2


def test_benchmark_packet_verify_helper(repo_root: Path) -> None:
    """Packet cases are structurally valid (no full index required)."""
    root = repo_root / PACKET_ROOT
    valid = root / "valid_release"
    if not valid.is_dir():
        return
    doc = json.loads((valid / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
    validate_benchmark_case(doc, policy_root=repo_root)
    invalid = root / "invalid_trace_hash_tamper"
    inv_doc = json.loads((invalid / BENCHMARK_CASE_NAME).read_text(encoding="utf-8"))
    assert inv_doc["expected_status"] == "failed"
    assert inv_doc["case_kind"] == "invalid_hash_mismatch"
