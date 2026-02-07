"""
Coverage integrity gate: for every required_bench risk_id there must be at least one
injection in the study spec that covers it (or the risk is waived). Strict mode exits 1;
non-strict writes summary/coverage_missing.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_study_runner import run_coordination_study


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_coverage_preflight_non_strict_writes_coverage_missing_json(tmp_path: Path) -> None:
    """When a required risk has no covering injection in spec, preflight writes coverage_missing.json (non-strict)."""
    repo = _repo_root()
    spec_path = repo / "tests" / "fixtures" / "coordination_study_smoke_spec.yaml"
    if not spec_path.exists():
        pytest.skip(f"Fixture spec not found: {spec_path}")
    matrix_path = repo / "policy" / "coordination" / "method_risk_matrix.v0.1.yaml"
    if not matrix_path.exists():
        pytest.skip("method_risk_matrix.v0.1.yaml not found")

    os.environ["LABTRUST_REPRO_SMOKE"] = "1"
    try:
        run_coordination_study(spec_path, tmp_path, repo_root=repo)
    finally:
        os.environ.pop("LABTRUST_REPRO_SMOKE", None)

    coverage_missing = tmp_path / "summary" / "coverage_missing.json"
    assert coverage_missing.exists(), "Preflight must write coverage_missing.json when coverage is missing"
    data = json.loads(coverage_missing.read_text(encoding="utf-8"))
    assert "missing" in data
    assert "required_risk_ids" in data
    assert "spec_injection_ids" in data
    assert len(data["missing"]) > 0, "Smoke spec has only INJ-COMMS-POISON-001 so many required risks are missing"
    for m in data["missing"]:
        assert "risk_id" in m
        assert "covering_injection_ids" in m
        assert "message" in m


def test_coverage_preflight_non_strict_deterministic(tmp_path: Path) -> None:
    """Two runs with same spec produce identical coverage_missing.json (deterministic)."""
    repo = _repo_root()
    spec_path = repo / "tests" / "fixtures" / "coordination_study_smoke_spec.yaml"
    if not spec_path.exists():
        pytest.skip(f"Fixture spec not found: {spec_path}")

    os.environ["LABTRUST_REPRO_SMOKE"] = "1"
    try:
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        run_coordination_study(spec_path, out1, repo_root=repo)
        run_coordination_study(spec_path, out2, repo_root=repo)
    finally:
        os.environ.pop("LABTRUST_REPRO_SMOKE", None)

    p1 = out1 / "summary" / "coverage_missing.json"
    p2 = out2 / "summary" / "coverage_missing.json"
    assert p1.exists() and p2.exists()
    raw1 = p1.read_text(encoding="utf-8")
    raw2 = p2.read_text(encoding="utf-8")
    assert raw1 == raw2, "coverage_missing.json must be deterministic across runs"


def test_coverage_preflight_strict_fails_when_missing(tmp_path: Path) -> None:
    """When LABTRUST_STRICT_COVERAGE=1 and a required risk has no injection in spec, run_coordination_study exits 1."""
    repo = _repo_root()
    spec_path = repo / "tests" / "fixtures" / "coordination_study_smoke_spec.yaml"
    if not spec_path.exists():
        pytest.skip(f"Fixture spec not found: {spec_path}")

    os.environ["LABTRUST_REPRO_SMOKE"] = "1"
    os.environ["LABTRUST_STRICT_COVERAGE"] = "1"
    try:
        with pytest.raises(SystemExit) as exc_info:
            run_coordination_study(spec_path, tmp_path, repo_root=repo)
        assert exc_info.value.code == 1
    finally:
        os.environ.pop("LABTRUST_REPRO_SMOKE", None)
        os.environ.pop("LABTRUST_STRICT_COVERAGE", None)
