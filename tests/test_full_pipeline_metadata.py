"""
Full pipeline metadata test: agentic + coord_risk with deterministic backend.

Runs run_benchmark with agent_driven=True, coord_method=llm_central_planner_agentic,
llm_backend=deterministic (no network). Asserts results and metadata shape
(estimated_cost_usd, mean_llm_latency_ms) for CI coverage of the full pipeline path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    from labtrust_gym.config import get_repo_root

    return Path(get_repo_root())


def test_full_pipeline_agentic_coord_risk_metadata_shape(tmp_path: Path) -> None:
    """Run coord_risk with agent_driven + llm_central_planner_agentic (deterministic); assert metadata keys."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    repo = _repo_root()
    scale = load_scale_config_by_id(repo, "small_smoke")
    out = tmp_path / "results.json"
    run_benchmark(
        task_name="coord_risk",
        num_episodes=1,
        base_seed=42,
        out_path=out,
        repo_root=repo,
        coord_method="llm_central_planner_agentic",
        agent_driven=True,
        llm_backend="deterministic",
        scale_config_override=scale,
        pipeline_mode="deterministic",
        injection_id="none",
    )
    assert out.exists()
    results = json.loads(out.read_text(encoding="utf-8"))
    assert "metadata" in results
    meta = results["metadata"]
    assert "estimated_cost_usd" in meta
    assert "mean_llm_latency_ms" in meta
    assert "episodes" in results
    assert len(results["episodes"]) == 1


def test_full_pipeline_smoke_script_deterministic(tmp_path: Path) -> None:
    """Run run_full_pipeline_smoke.py with --backend deterministic; assert summary exists and has expected columns."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    import subprocess

    repo = _repo_root()
    out_dir = tmp_path / "smoke_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "run_full_pipeline_smoke.py"),
            "--backend",
            "deterministic",
            "--methods",
            "llm_central_planner_agentic",
            "--episodes",
            "1",
            "--out",
            str(out_dir),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    summary_path = out_dir / "full_pipeline_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert isinstance(summary, list)
    assert len(summary) >= 1
    row = summary[0]
    assert "method_id" in row
    assert "success" in row
    assert "estimated_cost_usd" in row
    assert "mean_llm_latency_ms" in row
    assert row.get("success") is True
