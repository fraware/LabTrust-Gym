"""
Smoke test for coordination study runner: runs a tiny spec (2 methods, 1 scale, 1 injection, 1 episode)
and checks that output files exist. Determinism: same seed_base yields identical summary_coord.csv.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_study_runner import run_coordination_study


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_coordination_study_smoke_files_exist(tmp_path: Path) -> None:
    """Run coordination study with minimal spec; assert cells and summary files exist."""
    repo = _repo_root()
    spec_path = repo / "tests" / "fixtures" / "coordination_study_smoke_spec.yaml"
    if not spec_path.exists():
        pytest.skip(f"Fixture spec not found: {spec_path}")

    os.environ["LABTRUST_REPRO_SMOKE"] = "1"
    try:
        manifest = run_coordination_study(spec_path, tmp_path, repo_root=repo)
    finally:
        os.environ.pop("LABTRUST_REPRO_SMOKE", None)

    assert manifest.get("num_cells") == 2
    cell_ids = manifest.get("cell_ids") or []
    assert len(cell_ids) == 2

    for cell_id in cell_ids:
        results_path = tmp_path / "cells" / cell_id / "results.json"
        assert results_path.exists(), f"Missing {results_path}"
        data = results_path.read_text(encoding="utf-8")
        assert "schema_version" in data
        assert "episodes" in data
        assert "centralized_planner" in cell_id or "swarm_reactive" in cell_id
        assert "INJ-COMMS-POISON-001" in cell_id

    summary_csv = tmp_path / "summary" / "summary_coord.csv"
    assert summary_csv.exists(), f"Missing {summary_csv}"
    lines = summary_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2  # header + 2 data rows
    header = lines[0]
    for col in (
        "resilience.component_perf",
        "resilience.component_safety",
        "resilience.component_security",
        "resilience.component_coordination",
    ):
        assert col in header, f"summary_coord.csv missing column {col}"

    pareto_md = tmp_path / "summary" / "pareto.md"
    assert pareto_md.exists(), f"Missing {pareto_md}"
    content = pareto_md.read_text(encoding="utf-8")
    assert "Pareto" in content or "pareto" in content
    assert "Robust winner" in content or "robust" in content.lower()

    manifest_path = tmp_path / "manifest_coordination.json"
    assert manifest_path.exists(), f"Missing {manifest_path}"


def _normalize_csv_for_hash(content: str) -> bytes:
    """Normalize line endings to \\n so CSV hash is stable across platforms."""
    return content.strip().replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def test_coordination_study_same_seed_same_summary_coord_hash(tmp_path: Path) -> None:
    """Same seed_base and spec yield identical summary_coord.csv content (determinism)."""
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

    csv1 = out1 / "summary" / "summary_coord.csv"
    csv2 = out2 / "summary" / "summary_coord.csv"
    assert csv1.exists() and csv2.exists()
    raw1 = csv1.read_text(encoding="utf-8")
    raw2 = csv2.read_text(encoding="utf-8")
    norm1 = _normalize_csv_for_hash(raw1)
    norm2 = _normalize_csv_for_hash(raw2)
    h1 = hashlib.sha256(norm1).hexdigest()
    h2 = hashlib.sha256(norm2).hexdigest()
    assert h1 == h2, "Same seed_base and spec must yield identical summary_coord.csv (excluding timestamps)"


def test_coordination_study_legacy_injection_id_completes(tmp_path: Path) -> None:
    """Study spec with legacy injection_id (inj_tool_selection_noise) uses NoOpInjector and completes."""
    repo = _repo_root()
    spec_path = repo / "tests" / "fixtures" / "coordination_study_legacy_injection_spec.yaml"
    if not spec_path.exists():
        pytest.skip(f"Fixture spec not found: {spec_path}")

    os.environ["LABTRUST_REPRO_SMOKE"] = "1"
    try:
        manifest = run_coordination_study(spec_path, tmp_path, repo_root=repo)
    finally:
        os.environ.pop("LABTRUST_REPRO_SMOKE", None)

    assert manifest.get("num_cells") == 1
    cell_ids = manifest.get("cell_ids") or []
    assert len(cell_ids) == 1
    assert "inj_tool_selection_noise" in cell_ids[0]
    results_path = tmp_path / "cells" / cell_ids[0] / "results.json"
    assert results_path.exists(), f"Missing {results_path}"
    data = results_path.read_text(encoding="utf-8")
    assert "episodes" in data
