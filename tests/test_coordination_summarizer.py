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


def test_build_sota_leaderboard_hospital_lab_metrics() -> None:
    """When rows have perf.p95_tat, perf.on_time_rate, safety.critical_communication_compliance_rate they are aggregated correctly."""
    rows = [
        {
            "method_id": "m1",
            "perf.throughput": 2.0,
            "perf.p95_tat": 100.0,
            "perf.on_time_rate": 0.9,
            "safety.violations_total": 0,
            "safety.critical_communication_compliance_rate": 1.0,
            "robustness.resilience_score": 0.85,
            "sec.stealth_success_rate": 0.0,
        },
        {
            "method_id": "m1",
            "perf.throughput": 3.0,
            "perf.p95_tat": 120.0,
            "perf.on_time_rate": 0.8,
            "safety.violations_total": 1,
            "safety.critical_communication_compliance_rate": 0.5,
            "robustness.resilience_score": 0.75,
            "sec.stealth_success_rate": 0.0,
        },
    ]
    lb = build_sota_leaderboard(rows)
    assert len(lb) == 1
    r = lb[0]
    assert r["method_id"] == "m1"
    assert r["throughput_mean"] == 2.5
    assert r["p95_tat_mean"] == 110.0
    assert r["on_time_rate_mean"] == pytest.approx(0.85)
    assert r["critical_compliance_mean"] == pytest.approx(0.75)
    assert r["resilience_score_mean"] == pytest.approx(0.8)
    assert r["n_cells"] == 2


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


def test_run_summarize_pack_summary_with_hospital_lab_metrics(tmp_path: Path) -> None:
    """run_summarize reads pack_summary.csv with hospital-lab columns and writes leaderboard with p95_tat_mean, on_time_rate_mean, critical_compliance_mean."""
    (tmp_path / "summary").mkdir(parents=True, exist_ok=True)
    csv_path = tmp_path / "pack_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "method_id",
                "scale_id",
                "injection_id",
                "perf.throughput",
                "perf.p95_tat",
                "perf.on_time_rate",
                "safety.violations_total",
                "safety.critical_communication_compliance_rate",
                "robustness.resilience_score",
                "sec.stealth_success_rate",
            ],
            extrasaction="ignore",
        )
        w.writeheader()
        w.writerow(
            {
                "method_id": "kernel_whca",
                "scale_id": "small_smoke",
                "injection_id": "none",
                "perf.throughput": "1.5",
                "perf.p95_tat": "95.0",
                "perf.on_time_rate": "0.92",
                "safety.violations_total": "0",
                "safety.critical_communication_compliance_rate": "1.0",
                "robustness.resilience_score": "0.88",
                "sec.stealth_success_rate": "0",
            }
        )
    out_dir = tmp_path / "out"
    run_summarize(in_dir=tmp_path, out_dir=out_dir, repo_root=None)
    leaderboard_csv = out_dir / "summary" / "sota_leaderboard.csv"
    assert leaderboard_csv.exists()
    with leaderboard_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert "p95_tat_mean" in row
    assert "on_time_rate_mean" in row
    assert "critical_compliance_mean" in row
    assert float(row.get("p95_tat_mean") or 0) == 95.0
    assert abs(float(row.get("on_time_rate_mean") or 0) - 0.92) < 0.001
    assert abs(float(row.get("critical_compliance_mean") or 0) - 1.0) < 0.001
    md_content = (out_dir / "summary" / "sota_leaderboard.md").read_text()
    assert "p95_tat_mean" in md_content
    assert "on_time_rate_mean" in md_content
    assert "critical_compliance_mean" in md_content
    assert "hospital_lab_metrics" in md_content or "hospital-lab" in md_content.lower()
