"""
Tests for timing_mode as a first-class benchmark dimension.

- Same seed in explicit mode -> deterministic metrics.
- Same seed in simulated mode -> deterministic metrics.
- Utilization / queue metrics appear only in simulated mode (or None/0 in explicit).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.runner import run_benchmark


def test_explicit_mode_deterministic(tmp_path: Path) -> None:
    """Same seed in explicit mode produces identical episode metrics across two runs."""
    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")

    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    run_benchmark(
        task_name="TaskA",
        num_episodes=2,
        base_seed=100,
        out_path=out1,
        repo_root=repo,
        timing_mode="explicit",
    )
    run_benchmark(
        task_name="TaskA",
        num_episodes=2,
        base_seed=100,
        out_path=out2,
        repo_root=repo,
        timing_mode="explicit",
    )
    data1 = json.loads(out1.read_text(encoding="utf-8"))
    data2 = json.loads(out2.read_text(encoding="utf-8"))
    assert data1["config"].get("timing_mode") == "explicit"
    assert data2["config"].get("timing_mode") == "explicit"
    assert data1["seeds"] == data2["seeds"]
    for i, (ep1, ep2) in enumerate(zip(data1["episodes"], data2["episodes"])):
        assert ep1["seed"] == ep2["seed"], f"episode {i} seed"
        m1, m2 = ep1["metrics"], ep2["metrics"]
        assert m1.get("timing_mode") == "explicit"
        assert m1 == m2, f"episode {i} metrics differ: {m1} vs {m2}"


def test_simulated_mode_deterministic(tmp_path: Path) -> None:
    """Same seed in simulated mode produces identical episode metrics across two runs."""
    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")

    out1 = tmp_path / "run1_sim.json"
    out2 = tmp_path / "run2_sim.json"
    run_benchmark(
        task_name="TaskA",
        num_episodes=2,
        base_seed=200,
        out_path=out1,
        repo_root=repo,
        timing_mode="simulated",
    )
    run_benchmark(
        task_name="TaskA",
        num_episodes=2,
        base_seed=200,
        out_path=out2,
        repo_root=repo,
        timing_mode="simulated",
    )
    data1 = json.loads(out1.read_text(encoding="utf-8"))
    data2 = json.loads(out2.read_text(encoding="utf-8"))
    assert data1["config"].get("timing_mode") == "simulated"
    assert data2["config"].get("timing_mode") == "simulated"
    assert data1["seeds"] == data2["seeds"]
    for i, (ep1, ep2) in enumerate(zip(data1["episodes"], data2["episodes"])):
        assert ep1["seed"] == ep2["seed"], f"episode {i} seed"
        m1, m2 = ep1["metrics"], ep2["metrics"]
        assert m1.get("timing_mode") == "simulated"
        assert m1 == m2, f"episode {i} metrics differ: {m1} vs {m2}"


def test_utilization_metrics_only_in_simulated(tmp_path: Path) -> None:
    """device_utilization and device_queue_length_* in simulated; not (or None/0) in explicit."""
    repo = Path(__file__).resolve().parent.parent
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")

    out_explicit = tmp_path / "explicit.json"
    out_simulated = tmp_path / "simulated.json"
    run_benchmark(
        task_name="TaskA",
        num_episodes=1,
        base_seed=42,
        out_path=out_explicit,
        repo_root=repo,
        timing_mode="explicit",
    )
    run_benchmark(
        task_name="TaskA",
        num_episodes=1,
        base_seed=42,
        out_path=out_simulated,
        repo_root=repo,
        timing_mode="simulated",
    )
    data_explicit = json.loads(out_explicit.read_text(encoding="utf-8"))
    data_simulated = json.loads(out_simulated.read_text(encoding="utf-8"))
    metrics_explicit = data_explicit["episodes"][0]["metrics"]
    metrics_simulated = data_simulated["episodes"][0]["metrics"]

    assert metrics_explicit.get("timing_mode") == "explicit"
    assert metrics_simulated.get("timing_mode") == "simulated"

    # Explicit: no device_utilization / device_queue_length_* (or empty/0)
    assert "device_utilization" not in metrics_explicit or metrics_explicit.get("device_utilization") in (None, {})
    assert "device_queue_length_mean" not in metrics_explicit or metrics_explicit.get("device_queue_length_mean") in (
        None,
        {},
    )
    assert "device_queue_length_max" not in metrics_explicit or metrics_explicit.get("device_queue_length_max") in (
        None,
        {},
    )

    # Simulated: device_utilization and queue stats present (may be empty dict if no devices used)
    assert "device_utilization" in metrics_simulated
    assert "device_queue_length_mean" in metrics_simulated
    assert "device_queue_length_max" in metrics_simulated
    assert "p95_turnaround_s_note" in metrics_simulated
    assert "simulated" in (metrics_simulated.get("p95_turnaround_s_note") or "")
