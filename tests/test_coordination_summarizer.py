"""Tests for coordination summarizer: SOTA leaderboard and method-class comparison."""

import csv
from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_summarizer import (
    _comparison_class,
    _find_summary_csv,
    build_method_class_comparison,
    build_sota_leaderboard,
    run_summarize,
)


def test_find_summary_csv(tmp_path: Path) -> None:
    (tmp_path / "summary").mkdir()
    (tmp_path / "summary" / "summary_coord.csv").write_text("method_id\nm1\n")
    assert _find_summary_csv(tmp_path) == tmp_path / "summary" / "summary_coord.csv"
    (tmp_path / "summary" / "summary_coord.csv").unlink()
    (tmp_path / "summary_coord.csv").write_text("method_id\nm1\n")
    assert _find_summary_csv(tmp_path) == tmp_path / "summary_coord.csv"
    (tmp_path / "summary_coord.csv").unlink()
    assert _find_summary_csv(tmp_path) is None


def test_build_sota_leaderboard() -> None:
    rows = [
        {
            "method_id": "a",
            "perf.throughput": 1.0,
            "safety.violations_total": 0,
            "robustness.resilience_score": 0.8,
            "sec.stealth_success_rate": 0.0,
        },
        {
            "method_id": "a",
            "perf.throughput": 2.0,
            "safety.violations_total": 2,
            "robustness.resilience_score": 0.6,
            "sec.stealth_success_rate": 0.1,
        },
        {
            "method_id": "b",
            "perf.throughput": 0.5,
            "safety.violations_total": 10,
            "robustness.resilience_score": 0.5,
            "sec.stealth_success_rate": 0.2,
        },
    ]
    lb = build_sota_leaderboard(rows)
    assert len(lb) == 2
    a = next(r for r in lb if r["method_id"] == "a")
    assert a["throughput_mean"] == 1.5
    assert a["violations_mean"] == 1.0
    assert a["resilience_score_mean"] == 0.7
    assert a["stealth_success_rate_mean"] == 0.05
    assert a["n_cells"] == 2
    b = next(r for r in lb if r["method_id"] == "b")
    assert b["n_cells"] == 1


def test_comparison_class() -> None:
    assert _comparison_class("ripple_effect", None) == "ripple"
    assert _comparison_class("group_evolving_experience_sharing", None) == "evolving"
    assert _comparison_class("market_auction", None) == "auctions"
    assert _comparison_class("kernel_whca", None) == "kernel_schedulers"
    assert _comparison_class("centralized_planner", None) == "centralized"
    assert _comparison_class("unknown_method", None) == "other"


def test_build_method_class_comparison() -> None:
    rows = [
        {
            "method_id": "ripple_effect",
            "perf.throughput": 1.0,
            "safety.violations_total": 0,
            "robustness.resilience_score": 0.9,
            "sec.stealth_success_rate": 0.0,
        },
        {
            "method_id": "centralized_planner",
            "perf.throughput": 0.5,
            "safety.violations_total": 5,
            "robustness.resilience_score": 0.6,
            "sec.stealth_success_rate": 0.1,
        },
    ]
    comp = build_method_class_comparison(rows, None)
    classes = {r["method_class"]: r for r in comp}
    assert "ripple" in classes
    assert "centralized" in classes
    assert classes["ripple"]["resilience_score_mean"] == 0.9
    assert classes["centralized"]["violations_mean"] == 5.0


def test_run_summarize_writes_all_artifacts(tmp_path: Path) -> None:
    summary_dir = tmp_path / "summary"
    summary_dir.mkdir()
    csv_path = summary_dir / "summary_coord.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "method_id",
                "scale_id",
                "risk_id",
                "injection_id",
                "perf.throughput",
                "perf.p95_tat",
                "safety.violations_total",
                "sec.stealth_success_rate",
                "robustness.resilience_score",
            ],
            extrasaction="ignore",
        )
        w.writeheader()
        w.writerow(
            {
                "method_id": "ripple_effect",
                "scale_id": "s1",
                "risk_id": "R-1",
                "injection_id": "INJ-1",
                "perf.throughput": "0.5",
                "safety.violations_total": "0",
                "robustness.resilience_score": "0.75",
                "sec.stealth_success_rate": "0",
            }
        )
    out_dir = tmp_path / "out"
    run_summarize(in_dir=tmp_path, out_dir=out_dir, repo_root=None)
    assert (out_dir / "summary" / "sota_leaderboard.csv").exists()
    assert (out_dir / "summary" / "sota_leaderboard.md").exists()
    assert (out_dir / "summary" / "method_class_comparison.csv").exists()
    assert (out_dir / "summary" / "method_class_comparison.md").exists()
    content = (out_dir / "summary" / "sota_leaderboard.md").read_text()
    assert "ripple_effect" in content
    assert "throughput_mean" in content


def test_run_summarize_raises_when_no_csv(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No summary CSV"):
        run_summarize(in_dir=tmp_path, out_dir=tmp_path / "out", repo_root=None)
