"""
Tests for benchmark results schema v0.2 and summarize-results.

- Schema validation: run_benchmark output validates against results.v0.2.schema.json.
- Determinism: running summarize twice on same inputs yields identical summary.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.summarize import (
    load_results_from_path,
    summarize_results,
    run_summarize,
    rows_to_csv,
    validate_results_v02,
    _normalize_to_v02,
)


def test_results_v02_schema_validates_run_benchmark_output() -> None:
    """Output from run_benchmark (with schema_version and agent_baseline_id) validates against results.v0.2."""
    schema_path = Path("policy/schemas/results.v0.2.schema.json")
    if not schema_path.exists():
        pytest.skip("policy/schemas/results.v0.2.schema.json not found")
    # Minimal valid v0.2 result
    data = {
        "schema_version": "0.2",
        "task": "TaskA",
        "seeds": [42, 43],
        "episodes": [
            {"seed": 42, "metrics": {"throughput": 5, "p50_turnaround_s": 100.0, "steps": 100}},
            {"seed": 43, "metrics": {"throughput": 6, "p50_turnaround_s": 90.0, "steps": 100}},
        ],
        "agent_baseline_id": "scripted_ops_v1",
        "policy_fingerprint": None,
        "partner_id": None,
        "git_sha": "abc123",
    }
    errors = validate_results_v02(data, schema_path=schema_path)
    assert errors == [], f"Validation errors: {errors}"


def test_run_benchmark_output_validates_v02(tmp_path: Path) -> None:
    """Run benchmark writes results that validate against results.v0.2.schema.json."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")
    out_path = tmp_path / "results.json"
    run_benchmark(
        task_name="TaskA",
        num_episodes=2,
        base_seed=9999,
        out_path=out_path,
        repo_root=repo,
    )
    data = json.loads(out_path.read_text(encoding="utf-8"))
    schema_path = repo / "policy" / "schemas" / "results.v0.2.schema.json"
    if not schema_path.exists():
        pytest.skip("results.v0.2.schema.json not found")
    errors = validate_results_v02(data, schema_path=schema_path)
    assert errors == [], f"run_benchmark output should validate: {errors}"


def test_summarize_determinism(tmp_path: Path) -> None:
    """Running summarize twice on same inputs yields identical summary.csv."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    results_json = results_dir / "results.json"
    data = {
        "schema_version": "0.2",
        "task": "TaskA",
        "seeds": [42, 43],
        "episodes": [
            {"seed": 42, "metrics": {"throughput": 5, "p50_turnaround_s": 100.0, "steps": 100}},
            {"seed": 43, "metrics": {"throughput": 6, "p50_turnaround_s": 90.0, "steps": 100}},
        ],
        "agent_baseline_id": "scripted_ops_v1",
        "git_sha": "abc",
    }
    results_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    run_summarize([results_dir], out1, out_basename="summary")
    run_summarize([results_dir], out2, out_basename="summary")
    csv1 = (out1 / "summary.csv").read_text(encoding="utf-8")
    csv2 = (out2 / "summary.csv").read_text(encoding="utf-8")
    assert csv1 == csv2, "summary.csv must be identical for same inputs"


def test_summarize_aggregates_by_task_baseline_partner(tmp_path: Path) -> None:
    """Summarize groups by task + agent_baseline_id + partner_id and computes mean/std."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "results.json").write_text(
        json.dumps({
            "task": "TaskA",
            "seeds": [42, 43],
            "episodes": [
                {"seed": 42, "metrics": {"throughput": 10, "p50_turnaround_s": 100.0}},
                {"seed": 43, "metrics": {"throughput": 12, "p50_turnaround_s": 80.0}},
            ],
            "agent_baseline_id": "scripted_ops_v1",
        }, indent=2),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    csv_path, md_path = run_summarize([results_dir], out, out_basename="summary")
    assert csv_path.exists()
    assert md_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "task" in content
    assert "throughput_mean" in content
    assert "11" in content  # mean of 10 and 12
    rows = summarize_results(load_results_from_path(results_dir))
    assert len(rows) == 1
    assert rows[0]["task"] == "TaskA"
    assert rows[0]["throughput_mean"] == 11.0
    assert rows[0]["n_episodes"] == 2


def test_normalize_accepts_legacy_git_commit_hash() -> None:
    """Legacy results with git_commit_hash (no git_sha) normalize to v0.2 shape."""
    data = {
        "task": "TaskA",
        "episodes": [{"seed": 42, "metrics": {"throughput": 1}}],
        "git_commit_hash": "abc123",
    }
    norm = _normalize_to_v02(data)
    assert norm is not None
    assert norm.get("git_sha") == "abc123"
    assert norm.get("agent_baseline_id") == "scripted_ops_v1"
