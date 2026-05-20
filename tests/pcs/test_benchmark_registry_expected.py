"""LabTrust pcs-bench registry expected slice stays aligned with the generator."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.benchmark_pcs_bench import (
    PCS_BENCH_SUITE_ID,
    expected_pcs_bench_case_ids,
)

EXPECTED = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "pcs_qc_release"
    / "policy"
    / "benchmark_registry.labtrust-qc-release.expected.json"
)


def test_expected_registry_matches_generator() -> None:
    exp_valid, exp_invalid = expected_pcs_bench_case_ids()
    doc = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert doc["suite_id"] == PCS_BENCH_SUITE_ID
    assert sorted(doc["valid_cases"]) == sorted(exp_valid)
    assert sorted(doc["invalid_cases"]) == sorted(exp_invalid)
    assert len(doc["valid_cases"]) == 1
    assert len(doc["invalid_cases"]) == 12
