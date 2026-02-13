"""
Tests for labtrust determinism-report: run benchmark twice, assert v0.2 metrics
and episode log hash identical.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.determinism_report import run_determinism_report


@pytest.mark.slow
def test_determinism_report_small_run_passes(tmp_path: Path) -> None:
    """Small run (TaskA, episodes=2, seed=42) should pass determinism in CI."""
    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")
    passed, report, _ = run_determinism_report(
        task_name="throughput_sla",
        num_episodes=2,
        base_seed=42,
        out_dir=tmp_path,
        partner_id=None,
        timing_mode="explicit",
        repo_root=repo,
    )
    assert passed, f"Determinism report failed: {report.get('errors', [])}"
    assert report.get("passed") is True
    assert report.get("episode_log_identical") is True
    assert report.get("results_identical") is True
    assert report.get("v02_metrics_identical") is True
    r1, r2 = report["run1"], report["run2"]
    assert r1["episode_log_sha256"] == r2["episode_log_sha256"]
    assert r1["results_sha256"] == r2["results_sha256"]
    json_path = tmp_path / "determinism_report.json"
    md_path = tmp_path / "determinism_report.md"
    assert json_path.exists()
    assert md_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["passed"] is True
    assert "run1" in loaded and "run2" in loaded
    l1, l2 = loaded["run1"], loaded["run2"]
    assert l1["episode_log_sha256"] == l2["episode_log_sha256"]


@pytest.mark.slow
def test_determinism_report_cli(tmp_path: Path) -> None:
    """CLI determinism-report with TaskA/2/42 writes report and exits 0."""
    import subprocess
    import sys

    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")
    out_dir = tmp_path / "det_out"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "determinism-report",
            "--task",
            "throughput_sla",
            "--episodes",
            "2",
            "--seed",
            "42",
            "--out",
            str(out_dir),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
    )
    err = f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert proc.returncode == 0, err
    assert (out_dir / "determinism_report.json").exists()
    assert (out_dir / "determinism_report.md").exists()
    data = json.loads((out_dir / "determinism_report.json").read_text(encoding="utf-8"))
    assert data["passed"] is True


@pytest.mark.slow
def test_determinism_report_simulated_timing_passes(tmp_path: Path) -> None:
    """Determinism report with timing=simulated (device RNG seeded from --seed) passes."""
    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")
    passed, report, _ = run_determinism_report(
        task_name="throughput_sla",
        num_episodes=2,
        base_seed=99,
        out_dir=tmp_path,
        partner_id=None,
        timing_mode="simulated",
        repo_root=repo,
    )
    errs = report.get("errors", [])
    assert passed, f"Determinism (simulated) failed: {errs}"
    assert report.get("timing_mode") == "simulated"


@pytest.mark.slow
def test_determinism_report_taskg_kernel_passes(tmp_path: Path) -> None:
    """Determinism report for coord_scale with composed method kernel_centralized_edf passes."""
    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")
    passed, report, _ = run_determinism_report(
        task_name="coord_scale",
        num_episodes=2,
        base_seed=42,
        out_dir=tmp_path,
        partner_id=None,
        timing_mode="explicit",
        repo_root=repo,
        coord_method="kernel_centralized_edf",
    )
    errs = report.get("errors", [])
    assert passed, f"TaskG determinism failed: {errs}"
    assert report.get("coord_method") == "kernel_centralized_edf"
    assert report.get("episode_log_identical") is True
    assert report.get("results_identical") is True
    assert report.get("v02_metrics_identical") is True
