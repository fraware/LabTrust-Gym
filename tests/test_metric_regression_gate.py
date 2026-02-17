"""
Metric regression gate: compare current run to golden_metrics_baseline.json; fail if any metric regresses beyond threshold.

Runs when LABTRUST_CHECK_BASELINES=1. Uses benchmarks/baselines_official/v0.2/results/ as current
(or runs minimal benchmark when baseline dir present). Compares float/integer metrics with threshold_pct tolerance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _should_run_gate() -> bool:
    return os.environ.get("LABTRUST_CHECK_BASELINES") == "1"


def _load_golden_baseline(repo: Path) -> dict | None:
    path = repo / "benchmarks" / "baselines_official" / "v0.2" / "golden_metrics_baseline.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _mean_metric_from_result_file(path: Path, metric_key: str) -> float | None:
    """Compute mean of metric_key across episodes; return None if missing."""
    data = json.loads(path.read_text(encoding="utf-8"))
    episodes = data.get("episodes") or []
    if not episodes:
        return None
    vals = []
    for ep in episodes:
        m = (ep.get("metrics") or {}).get(metric_key)
        if m is not None and isinstance(m, (int, float)):
            vals.append(float(m))
    if not vals:
        return None
    return sum(vals) / len(vals)


@pytest.mark.slow
def test_metric_regression_gate() -> None:
    """
    Compare official v0.2 results to golden_metrics_baseline; fail if any metric regresses beyond threshold_pct.
    Set LABTRUST_CHECK_BASELINES=1 to run.
    """
    if not _should_run_gate():
        pytest.skip("Set LABTRUST_CHECK_BASELINES=1 to run metric regression gate")
    repo = _repo_root()
    golden = _load_golden_baseline(repo)
    if not golden or not golden.get("metrics"):
        pytest.skip("No golden_metrics_baseline.json or empty metrics")
    results_dir = repo / "benchmarks" / "baselines_official" / "v0.2" / "results"
    if not results_dir.is_dir():
        pytest.skip("No v0.2 results dir; run generate-official-baselines first")
    failures = []
    for entry in golden["metrics"]:
        pattern = entry.get("task_file_pattern") or ""
        metric_key = entry.get("metric_key") or ""
        baseline = entry.get("baseline")
        threshold_pct = float(entry.get("threshold_pct", 5))
        higher_is_better = entry.get("higher_is_better", True)
        if not pattern or metric_key is None or baseline is None:
            continue
        candidates = list(results_dir.glob(f"{pattern}.json"))
        if not candidates:
            continue
        path = candidates[0]
        current = _mean_metric_from_result_file(path, metric_key)
        if current is None:
            failures.append(f"{pattern} {metric_key}: no current value (missing in episodes)")
            continue
        baseline_f = float(baseline)
        if higher_is_better:
            min_ok = baseline_f * (1 - threshold_pct / 100.0)
            if current < min_ok:
                failures.append(
                    f"{pattern} {metric_key}: current={current} < baseline*(1-{threshold_pct}%)={min_ok} (higher is better)"
                )
        else:
            max_ok = baseline_f * (1 + threshold_pct / 100.0)
            if current > max_ok:
                failures.append(
                    f"{pattern} {metric_key}: current={current} > baseline*(1+{threshold_pct}%)={max_ok} (lower is better)"
                )
    if failures:
        pytest.fail("Metric regression (threshold):\n  " + "\n  ".join(failures))
