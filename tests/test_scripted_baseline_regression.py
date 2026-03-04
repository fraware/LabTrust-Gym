"""
Regression test for scripted baseline: fixed task and seed produce stable metrics.

Scripted baseline behaviour is the stable reference for SOTA comparison; this test
locks throughput_sla with seed 42 so changes to scripted ops/runner are detected.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.runner import run_benchmark

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "scripted_baseline"
GOLDEN_FILE = GOLDEN_DIR / "golden_throughput_sla_seed42.json"


def test_scripted_baseline_throughput_sla_seed42_regression(tmp_path: Path) -> None:
    """Run throughput_sla with seed 42 and assert metrics match golden."""
    out_path = tmp_path / "results.json"
    run_benchmark(
        task_name="throughput_sla",
        num_episodes=1,
        base_seed=42,
        out_path=out_path,
    )
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["task"] == "throughput_sla"
    assert len(data["episodes"]) == 1
    metrics = data["episodes"][0]["metrics"]
    throughput = metrics.get("throughput", 0)
    steps = metrics.get("steps", 0)

    assert GOLDEN_FILE.exists(), "Golden file missing; run once and commit golden."
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    expected = golden["episode_metrics"]
    assert throughput == expected["throughput"], (
        f"Scripted baseline regression: throughput {throughput} != golden {expected['throughput']}"
    )
    assert steps == expected["steps"], f"Scripted baseline regression: steps {steps} != golden {expected['steps']}"
