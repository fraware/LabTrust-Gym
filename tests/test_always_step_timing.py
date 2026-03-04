"""Tests for always_record_step_timing (8.1): metadata.step_timing and run_duration_wall_s when flag is set."""

from __future__ import annotations

import tempfile
from pathlib import Path

from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_always_record_step_timing_metadata_present() -> None:
    """With always_record_step_timing=True and deterministic pipeline, metadata has step_timing and run_duration_wall_s."""
    repo = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results.json"
        results = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=repo,
            coord_method="centralized_planner",
            pipeline_mode="deterministic",
            allow_network=False,
            always_record_step_timing=True,
        )
        meta = results.get("metadata") or {}
        assert "step_timing" in meta, "step_timing must be present when always_record_step_timing=True"
        step_timing = meta["step_timing"]
        assert "step_ms_mean" in step_timing
        assert "step_ms_p95" in step_timing
        assert isinstance(step_timing["step_ms_mean"], (int, float))
        assert isinstance(step_timing["step_ms_p95"], (int, float))
        assert "run_duration_wall_s" in meta
        assert meta["run_duration_wall_s"] > 0, "run_duration_wall_s must be > 0 when always_record_step_timing=True"


def test_deterministic_without_always_step_timing_no_timing_metadata() -> None:
    """With always_record_step_timing=False (default) and deterministic, step_timing absent and run_duration_wall_s is 0."""
    repo = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results.json"
        results = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=repo,
            coord_method="centralized_planner",
            pipeline_mode="deterministic",
            allow_network=False,
            always_record_step_timing=False,
        )
        meta = results.get("metadata") or {}
        assert results.get("non_deterministic") is False
        assert meta.get("run_duration_wall_s") == 0
        assert "step_timing" not in meta or meta.get("step_timing") is None
