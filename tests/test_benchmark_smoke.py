"""
Benchmark smoke tests: run 2 episodes quickly, ensure deterministic outputs for same seed.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.benchmarks.tasks import get_task


def test_benchmark_run_2_episodes_smoke() -> None:
    """Run 2 episodes for TaskA; no crash; results.json has 2 episodes."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        run_benchmark(
            task_name="TaskA",
            num_episodes=2,
            base_seed=42,
            out_path=out,
        )
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["task"] == "TaskA"
        assert data["num_episodes"] == 2
        assert len(data["episodes"]) == 2
        assert "seeds" in data
        assert data["seeds"] == [42, 43]
        for ep in data["episodes"]:
            assert "seed" in ep
            assert "metrics" in ep
            assert "throughput" in ep["metrics"]
            assert "steps" in ep["metrics"]


def test_benchmark_determinism_same_seed() -> None:
    """Same task and base_seed produce identical episode metrics across two runs."""
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "run1.json"
        out2 = Path(tmp) / "run2.json"
        run_benchmark(
            task_name="TaskA",
            num_episodes=2,
            base_seed=100,
            out_path=out1,
        )
        run_benchmark(
            task_name="TaskA",
            num_episodes=2,
            base_seed=100,
            out_path=out2,
        )
        data1 = json.loads(out1.read_text(encoding="utf-8"))
        data2 = json.loads(out2.read_text(encoding="utf-8"))
        assert data1["seeds"] == data2["seeds"]
        for i, (ep1, ep2) in enumerate(zip(data1["episodes"], data2["episodes"])):
            assert ep1["seed"] == ep2["seed"], f"episode {i} seed"
            assert ep1["metrics"] == ep2["metrics"], (
                f"episode {i} metrics differ: {ep1['metrics']} vs {ep2['metrics']}"
            )


def test_task_initial_state_deterministic() -> None:
    """Task get_initial_state(seed) is deterministic."""
    task = get_task("TaskA")
    s1 = task.get_initial_state(99)
    s2 = task.get_initial_state(99)
    assert s1 == s2
    s3 = task.get_initial_state(100)
    assert s1 != s3 or s1 == s3
