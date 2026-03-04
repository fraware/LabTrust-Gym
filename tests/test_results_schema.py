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
    _build_llm_economics_rows,
    _load_raw_results_with_metadata,
    _normalize_to_v02,
    iter_results_and_metadata_from_paths,
    load_results_from_path,
    run_summarize,
    summarize_results,
    summarize_results_streaming,
    summarize_results_v03,
    validate_results_v02,
    validate_results_v03,
)


def test_results_v02_schema_validates_run_benchmark_output() -> None:
    """Output from run_benchmark (with schema_version and agent_baseline_id) validates against results.v0.2."""
    schema_path = Path("policy/schemas/results.v0.2.schema.json")
    if not schema_path.exists():
        pytest.skip("policy/schemas/results.v0.2.schema.json not found")
    # Minimal valid v0.2 result
    data = {
        "schema_version": "0.2",
        "task": "throughput_sla",
        "seeds": [42, 43],
        "episodes": [
            {
                "seed": 42,
                "metrics": {"throughput": 5, "p50_turnaround_s": 100.0, "steps": 100},
            },
            {
                "seed": 43,
                "metrics": {"throughput": 6, "p50_turnaround_s": 90.0, "steps": 100},
            },
        ],
        "agent_baseline_id": "scripted_ops_v1",
        "policy_fingerprint": None,
        "partner_id": None,
        "git_sha": "abc123",
    }
    errors = validate_results_v02(data, schema_path=schema_path)
    assert errors == [], f"Validation errors: {errors}"


def test_results_v02_schema_validates_with_metadata_llm() -> None:
    """Results with optional metadata (llm_backend_id, etc.) still validate against results.v0.2."""
    schema_path = Path("policy/schemas/results.v0.2.schema.json")
    if not schema_path.exists():
        pytest.skip("policy/schemas/results.v0.2.schema.json not found")
    data = {
        "schema_version": "0.2",
        "task": "throughput_sla",
        "seeds": [42],
        "episodes": [{"seed": 42, "metrics": {"throughput": 0, "steps": 10}}],
        "agent_baseline_id": "llm_safe_v1",
        "policy_fingerprint": None,
        "partner_id": None,
        "git_sha": None,
        "metadata": {
            "llm_backend_id": "deterministic_constrained",
            "llm_model_id": "n/a",
            "llm_error_rate": 0.0,
            "mean_llm_latency_ms": None,
        },
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
        task_name="throughput_sla",
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
        "task": "throughput_sla",
        "seeds": [42, 43],
        "episodes": [
            {
                "seed": 42,
                "metrics": {"throughput": 5, "p50_turnaround_s": 100.0, "steps": 100},
            },
            {
                "seed": 43,
                "metrics": {"throughput": 6, "p50_turnaround_s": 90.0, "steps": 100},
            },
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
        json.dumps(
            {
                "task": "throughput_sla",
                "seeds": [42, 43],
                "episodes": [
                    {
                        "seed": 42,
                        "metrics": {"throughput": 10, "p50_turnaround_s": 100.0},
                    },
                    {
                        "seed": 43,
                        "metrics": {"throughput": 12, "p50_turnaround_s": 80.0},
                    },
                ],
                "agent_baseline_id": "scripted_ops_v1",
            },
            indent=2,
        ),
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
    assert rows[0]["task"] == "throughput_sla"
    assert rows[0]["throughput_mean"] == 11.0
    assert rows[0]["n_episodes"] == 2


def test_summarize_writes_llm_economics_when_metadata_has_llm_backend(
    tmp_path: Path,
) -> None:
    """When result has metadata.llm_backend_id, run_summarize writes llm_economics.csv and .md."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "results.json").write_text(
        json.dumps(
            {
                "task": "throughput_sla",
                "seeds": [42],
                "episodes": [{"seed": 42, "metrics": {"throughput": 5}}],
                "agent_baseline_id": "llm_live_openai_v1",
                "metadata": {
                    "llm_backend_id": "openai_live",
                    "llm_model_id": "gpt-4o-mini",
                    "total_tokens": 1000,
                    "tokens_per_step": 50.0,
                    "estimated_cost_usd": 0.001,
                    "mean_llm_latency_ms": 200.0,
                    "p50_llm_latency_ms": 180.0,
                    "p95_llm_latency_ms": 400.0,
                    "llm_error_rate": 0.0,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    run_summarize([results_dir], out, out_basename="summary")
    assert (out / "llm_economics.csv").exists()
    assert (out / "llm_economics.md").exists()
    raw = _load_raw_results_with_metadata([results_dir])
    rows = _build_llm_economics_rows(raw)
    assert len(rows) == 1
    assert rows[0]["llm_backend_id"] == "openai_live"
    assert rows[0]["total_tokens"] == 1000
    assert rows[0]["estimated_cost_usd"] == 0.001


def test_normalize_accepts_legacy_git_commit_hash() -> None:
    """Legacy results with git_commit_hash (no git_sha) normalize to v0.2 shape."""
    data = {
        "task": "throughput_sla",
        "episodes": [{"seed": 42, "metrics": {"throughput": 1}}],
        "git_commit_hash": "abc123",
    }
    norm = _normalize_to_v02(data)
    assert norm is not None
    assert norm.get("git_sha") == "abc123"
    assert norm.get("agent_baseline_id") == "scripted_ops_v1"


def test_results_v03_schema_validates() -> None:
    """A v0.3 document (with optional quantiles/CI) validates against results.v0.3.schema.json."""
    schema_path = Path("policy/schemas/results.v0.3.schema.json")
    if not schema_path.exists():
        pytest.skip("policy/schemas/results.v0.3.schema.json not found")
    data = {
        "schema_version": "0.3",
        "task": "throughput_sla",
        "seeds": [42, 43],
        "episodes": [
            {
                "seed": 42,
                "metrics": {
                    "throughput": 5,
                    "p50_turnaround_s": 100.0,
                    "p95_turnaround_s": 120.0,
                    "turnaround_quantiles_s": {
                        "p10": 80,
                        "p25": 90,
                        "p50": 100,
                        "p75": 110,
                        "p90": 120,
                    },
                    "throughput_ci_95": {"lower": 4.0, "upper": 6.0},
                },
            },
            {
                "seed": 43,
                "metrics": {
                    "throughput": 6,
                    "p50_turnaround_s": 90.0,
                    "p95_turnaround_s": 115.0,
                },
            },
        ],
        "agent_baseline_id": "scripted_ops_v1",
        "policy_fingerprint": None,
        "partner_id": None,
        "git_sha": "abc123",
    }
    errors = validate_results_v03(data, schema_path=schema_path)
    assert errors == [], f"Validation errors: {errors}"


def test_summarize_v02_output_unchanged_for_fixture(tmp_path: Path) -> None:
    """For a fixed fixture, summary_v0.2.csv is deterministic and preserves CI-stable semantics."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    fixture = {
        "schema_version": "0.2",
        "task": "throughput_sla",
        "seeds": [42, 43],
        "episodes": [
            {
                "seed": 42,
                "metrics": {"throughput": 10, "p50_turnaround_s": 100.0, "steps": 100},
            },
            {
                "seed": 43,
                "metrics": {"throughput": 12, "p50_turnaround_s": 80.0, "steps": 100},
            },
        ],
        "agent_baseline_id": "scripted_ops_v1",
        "git_sha": "abc",
    }
    (results_dir / "results.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    run_summarize([results_dir], out1, out_basename="summary")
    run_summarize([results_dir], out2, out_basename="summary")
    csv_v02_1 = (out1 / "summary_v0.2.csv").read_text(encoding="utf-8")
    csv_v02_2 = (out2 / "summary_v0.2.csv").read_text(encoding="utf-8")
    assert csv_v02_1 == csv_v02_2, "summary_v0.2.csv must be identical for same inputs (determinism)"
    assert out1 / "summary_v0.2.csv" in list(out1.iterdir())
    assert out1 / "summary_v0.3.csv" in list(out1.iterdir())
    assert (out1 / "summary.csv").read_text(encoding="utf-8") == csv_v02_1, "summary.csv must equal summary_v0.2.csv"
    rows = summarize_results(load_results_from_path(results_dir))
    assert len(rows) == 1
    assert rows[0]["task"] == "throughput_sla"
    assert rows[0]["n_episodes"] == 2
    assert rows[0]["throughput_mean"] == 11.0
    assert rows[0]["throughput_std"] == pytest.approx(2**0.5)  # sample stdev of [10, 12]
    assert rows[0]["p50_turnaround_s_mean"] == 90.0


def test_summarize_v03_has_quantiles_and_ci(tmp_path: Path) -> None:
    """summary_v0.3.csv contains paper-grade columns: quantiles and 95% CI."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "results.json").write_text(
        json.dumps(
            {
                "schema_version": "0.2",
                "task": "throughput_sla",
                "seeds": [42, 43],
                "episodes": [
                    {
                        "seed": 42,
                        "metrics": {"throughput": 10, "p50_turnaround_s": 100.0},
                    },
                    {
                        "seed": 43,
                        "metrics": {"throughput": 12, "p50_turnaround_s": 80.0},
                    },
                ],
                "agent_baseline_id": "scripted_ops_v1",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    run_summarize([results_dir], tmp_path / "out", out_basename="summary")
    csv_v03 = (tmp_path / "out" / "summary_v0.3.csv").read_text(encoding="utf-8")
    assert "throughput_p50" in csv_v03
    assert "throughput_p90" in csv_v03
    assert "throughput_mean_ci_lower" in csv_v03
    assert "throughput_mean_ci_upper" in csv_v03
    assert "p50_turnaround_s_p50" in csv_v03
    assert "p50_turnaround_s_mean_ci_lower" in csv_v03
    rows_v03 = summarize_results_v03(load_results_from_path(results_dir))
    assert len(rows_v03) == 1
    assert "throughput_p50" in rows_v03[0]
    assert rows_v03[0]["throughput_p50"] == 11.0
    assert rows_v03[0]["throughput_p90"] is not None
    assert rows_v03[0]["throughput_mean_ci_lower"] is not None
    assert rows_v03[0]["throughput_mean_ci_upper"] is not None


def test_summarize_streaming_large_result_dir_bounded_memory(tmp_path: Path) -> None:
    """
    run_summarize on a large-ish synthetic result dir (many files) completes and produces
    correct aggregates. Previously would spike memory by loading all results at once;
    streaming path keeps memory bounded (one file at a time + grouped episodes only).
    """
    n_files = 200
    results_dir = tmp_path / "many_results"
    results_dir.mkdir()
    for i in range(n_files):
        data = {
            "task": "throughput_sla",
            "seeds": [42 + i],
            "episodes": [
                {"seed": 42 + i, "metrics": {"throughput": 5 + (i % 3), "steps": 100}},
            ],
            "agent_baseline_id": "scripted_ops_v1",
            "partner_id": None,
        }
        (results_dir / f"results_{i:04d}.json").write_text(json.dumps(data), encoding="utf-8")
    out_dir = tmp_path / "out"
    csv_path, md_path = run_summarize([results_dir], out_dir, out_basename="summary")
    assert csv_path.exists()
    assert md_path.exists()
    rows = summarize_results(load_results_from_path(results_dir))
    assert len(rows) == 1
    assert rows[0]["n_episodes"] == n_files
    assert rows[0]["task"] == "throughput_sla"
    stream_rows_v02, stream_rows_v03, _, _ = summarize_results_streaming(
        iter_results_and_metadata_from_paths([results_dir])
    )
    assert len(stream_rows_v02) == 1
    assert stream_rows_v02[0]["n_episodes"] == n_files
    assert stream_rows_v02[0]["throughput_mean"] == rows[0]["throughput_mean"]
    assert len(stream_rows_v03) == 1
    assert stream_rows_v03[0]["n_episodes"] == n_files
