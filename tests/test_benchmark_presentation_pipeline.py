"""Tests for benchmark presentation analytics helpers."""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.benchmarks.presentation.pipeline import (
    compute_run_analytics,
    default_report_out_dir,
    load_run_meta,
    load_run_summary,
    write_methods_matrix_csv,
)


def test_default_report_out_dir(tmp_path: Path) -> None:
    r = tmp_path / "nested" / "my_run"
    r.mkdir(parents=True)
    assert default_report_out_dir(r) == tmp_path / "nested" / "my_run_report"


def test_load_run_meta_missing(tmp_path: Path) -> None:
    assert load_run_meta(tmp_path) == {}


def test_load_run_summary_missing(tmp_path: Path) -> None:
    assert load_run_summary(tmp_path) is None


def test_compute_run_analytics_basic() -> None:
    rows = [
        {
            "method": "a",
            "status": "PASS",
            "duration_s": 3600.0,
            "llm_calls": 10,
            "metadata_total_tokens": 100,
            "enrich": {
                "mean_throughput": 0.0,
                "mean_resilience": 0.5,
                "total_transport_consignment": 0,
            },
        },
        {
            "method": "b",
            "status": "PENDING",
            "duration_s": None,
            "llm_calls": None,
            "metadata_total_tokens": None,
            "enrich": None,
        },
    ]
    a = compute_run_analytics(rows)
    assert a["row_count"] == 2
    assert a["by_status"]["PASS"] == 1
    assert a["by_status"]["PENDING"] == 1
    assert a["sum_llm_calls"] == 10
    assert a["sum_metadata_tokens"] == 100
    assert a["total_wall_clock_hours"] == 1.0
    assert a["longest_method_wall"]["method"] == "a"


def test_write_methods_matrix_csv_roundtrip(tmp_path: Path) -> None:
    rows = [
        {
            "method": "m1",
            "family": "classical",
            "status": "PASS",
            "duration_s": 10.0,
            "llm_model_id": None,
            "llm_calls": None,
            "metadata_total_tokens": None,
            "llm_error_rate": None,
            "ended_at": "2026-01-01T00:00:00+00:00",
            "result_path": str(tmp_path / "results.json"),
            "enrich": {
                "num_episodes": 2,
                "mean_throughput": 0.0,
                "mean_resilience": 0.5,
                "total_transport_consignment": 0,
            },
        }
    ]
    out = tmp_path / "m.csv"
    write_methods_matrix_csv(out, rows)
    text = out.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    assert len(lines) == 2
    assert "m1" in lines[1]
    assert "classical" in lines[1]
