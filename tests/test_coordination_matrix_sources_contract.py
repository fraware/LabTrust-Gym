"""
Contract tests for coordination matrix metric sources.

Ensures: required columns enforced, no duplicate keys, attacked aggregation (worst-case) stable.
See docs/coordination_matrix_contract.md (Sources contract section).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_matrix_builder import (
    CANONICAL_ATTACKED_SOURCE,
    CANONICAL_CLEAN_SOURCE,
    build_coordination_matrix,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _fixture_run_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "coordination_matrix_run_fixture"


@pytest.fixture
def run_fixture_dir() -> Path:
    """Path to coordination_matrix_run_fixture; skip if missing."""
    d = _fixture_run_dir()
    if not (d / CANONICAL_CLEAN_SOURCE).exists():
        pytest.skip("coordination_matrix_run_fixture not present")
    return d


def test_canonical_clean_missing_fails_with_precise_message(tmp_path: Path, run_fixture_dir: Path) -> None:
    """When canonical clean source is missing, build fails with metric_id, sources, key columns."""
    shutil.copy(run_fixture_dir / "metadata.json", tmp_path / "metadata.json")
    # Do not copy summary_coord.csv; do not add pack_summary so attack path may still require it
    (tmp_path / CANONICAL_ATTACKED_SOURCE).write_text(
        "scale_id,method_id,injection_id,attack_success_rate,sec.stealth_success_rate,sec.time_to_attribution_steps,sec.blast_radius_proxy,fallback_rate\n"
        "s,m,i,0,0,0,0,0\n",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError) as exc_info:
        build_coordination_matrix(tmp_path, tmp_path / "out.json", strict=True)
    msg = str(exc_info.value)
    assert CANONICAL_CLEAN_SOURCE in msg
    assert "scale_id" in msg or "method_id" in msg


def test_canonical_clean_required_columns_missing(tmp_path: Path, run_fixture_dir: Path) -> None:
    """If canonical clean summary is missing a required key column, build fails with precise message."""
    shutil.copy(run_fixture_dir / "metadata.json", tmp_path / "metadata.json")
    shutil.copy(run_fixture_dir / "pack_summary.csv", tmp_path / CANONICAL_ATTACKED_SOURCE)
    # Write summary_coord.csv without method_id
    (tmp_path / CANONICAL_CLEAN_SOURCE).write_text(
        "scale_id,p95_tat_s,throughput_per_hr,violation_rate,mean_llm_latency_ms,estimated_cost_usd\n"
        "corridor_heavy,100,80,0.005,200,0.10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc_info:
        build_coordination_matrix(tmp_path, tmp_path / "out.json", strict=True)
    msg = str(exc_info.value).lower()
    assert "method_id" in msg or "key column" in msg
    assert "clean" in msg


def test_canonical_clean_duplicate_keys(tmp_path: Path, run_fixture_dir: Path) -> None:
    """If canonical clean summary has duplicate (scale_id, method_id), build fails with duplicate key."""
    shutil.copy(run_fixture_dir / "metadata.json", tmp_path / "metadata.json")
    shutil.copy(run_fixture_dir / "pack_summary.csv", tmp_path / CANONICAL_ATTACKED_SOURCE)
    # Two rows with same scale_id, method_id
    (tmp_path / CANONICAL_CLEAN_SOURCE).write_text(
        "scale_id,method_id,p95_tat_s,throughput_per_hr,violation_rate,mean_llm_latency_ms,estimated_cost_usd\n"
        "corridor_heavy,llm_central_planner,100,80,0.005,200,0.10\n"
        "corridor_heavy,llm_central_planner,99,81,0.006,199,0.09\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc_info:
        build_coordination_matrix(tmp_path, tmp_path / "out.json", strict=True)
    msg = str(exc_info.value).lower()
    assert "duplicate" in msg
    assert "clean" in msg


def test_canonical_clean_missing_metric_column(tmp_path: Path, run_fixture_dir: Path) -> None:
    """If canonical clean summary has no candidate column for a required metric, build fails with metric_id and attempted columns."""
    shutil.copy(run_fixture_dir / "metadata.json", tmp_path / "metadata.json")
    shutil.copy(run_fixture_dir / "pack_summary.csv", tmp_path / CANONICAL_ATTACKED_SOURCE)
    # Omit p95_tat_s (and any alias); keep other columns
    (tmp_path / CANONICAL_CLEAN_SOURCE).write_text(
        "scale_id,method_id,throughput_per_hr,violation_rate,mean_llm_latency_ms,estimated_cost_usd\n"
        "corridor_heavy,llm_central_planner,80,0.005,200,0.10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc_info:
        build_coordination_matrix(tmp_path, tmp_path / "out.json", strict=True)
    msg = str(exc_info.value).lower()
    assert "p95_tat_s" in msg or "candidates" in msg or "attempted" in msg


def test_canonical_attacked_duplicate_keys(tmp_path: Path, run_fixture_dir: Path) -> None:
    """If canonical attacked summary has duplicate (scale_id, method_id, injection_id), build fails."""
    shutil.copy(run_fixture_dir / "metadata.json", tmp_path / "metadata.json")
    shutil.copy(run_fixture_dir / "summary_coord.csv", tmp_path / CANONICAL_CLEAN_SOURCE)
    # Duplicate injection_id for same scale_id, method_id
    (tmp_path / CANONICAL_ATTACKED_SOURCE).write_text(
        "scale_id,method_id,injection_id,attack_success_rate,sec.stealth_success_rate,sec.time_to_attribution_steps,sec.blast_radius_proxy,fallback_rate\n"
        "corridor_heavy,llm_central_planner,inj_A,0.10,0.05,20,1.5,0.01\n"
        "corridor_heavy,llm_central_planner,inj_A,0.12,0.06,21,1.6,0.02\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc_info:
        build_coordination_matrix(tmp_path, tmp_path / "out.json", strict=True)
    msg = str(exc_info.value).lower()
    assert "duplicate" in msg
    assert "attacked" in msg


def test_attacked_aggregation_worst_case(tmp_path: Path, run_fixture_dir: Path) -> None:
    """Attacked metrics aggregate by worst-case: lower_is_better -> max across injections."""
    shutil.copytree(run_fixture_dir, tmp_path, dirs_exist_ok=True)
    out_path = tmp_path / "coordination_matrix.json"
    matrix = build_coordination_matrix(tmp_path, out_path, strict=True)
    # Fixture has corridor_heavy + llm_central_planner with inj_A (0.10) and inj_B (0.25); worst = 0.25
    rows = matrix.get("rows") or []
    cell = next(
        (r for r in rows if r.get("scale_id") == "corridor_heavy" and r.get("method_id") == "llm_central_planner"),
        None,
    )
    assert cell is not None
    attacked = cell.get("metrics", {}).get("attacked") or {}
    assert "attack_success_rate" in attacked
    assert attacked["attack_success_rate"] == 0.25


def test_canonical_source_preferred_when_both_exist(tmp_path: Path, run_fixture_dir: Path) -> None:
    """When both canonical and non-canonical clean files exist, builder uses only canonical."""
    shutil.copytree(run_fixture_dir, tmp_path, dirs_exist_ok=True)
    # Add a non-canonical file with different data (would change matrix if used)
    (tmp_path / "results.json").write_text(
        '[{"scale_id":"corridor_heavy","method_id":"llm_central_planner","p95_tat_s":999}]',
        encoding="utf-8",
    )
    out_path = tmp_path / "matrix.json"
    matrix = build_coordination_matrix(tmp_path, out_path, strict=True)
    # Matrix should reflect summary_coord.csv (100 for p95_tat_s), not results.json (999)
    rows = matrix.get("rows") or []
    cell = next(
        (r for r in rows if r.get("scale_id") == "corridor_heavy" and r.get("method_id") == "llm_central_planner"),
        None,
    )
    assert cell is not None
    clean = cell.get("metrics", {}).get("clean") or {}
    assert clean.get("p95_tat_s") == 100.0
