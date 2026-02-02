"""
Partner overlay effects: sanity assertions for hsl_like.

- Run one episode TaskA simulated with default partner and with hsl_like.
- Assert device_utilization exists in simulated mode.
- Assert the two runs differ (overlay effect: policy_fingerprint or metrics).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_partner_overlay_simulated_device_utilization_and_differ(
    tmp_path: Path,
) -> None:
    """
    Run one episode TaskA simulated with default partner and with hsl_like.
    Assert device_utilization exists in episode metrics; assert the two runs differ.
    """
    repo = _repo_root()
    if not (repo / "policy" / "partners" / "hsl_like").is_dir():
        pytest.skip("policy/partners/hsl_like not found")

    out_default = tmp_path / "default.json"
    out_hsl = tmp_path / "hsl_like.json"
    seed = 7777
    run_benchmark(
        task_name="TaskA",
        num_episodes=1,
        base_seed=seed,
        out_path=out_default,
        repo_root=repo,
        partner_id=None,
        timing_mode="simulated",
    )
    run_benchmark(
        task_name="TaskA",
        num_episodes=1,
        base_seed=seed,
        out_path=out_hsl,
        repo_root=repo,
        partner_id="hsl_like",
        timing_mode="simulated",
    )

    data_default = json.loads(out_default.read_text(encoding="utf-8"))
    data_hsl = json.loads(out_hsl.read_text(encoding="utf-8"))
    assert data_default["config"].get("timing_mode") == "simulated"
    assert data_hsl["config"].get("timing_mode") == "simulated"
    assert len(data_default["episodes"]) == 1
    assert len(data_hsl["episodes"]) == 1

    metrics_default = data_default["episodes"][0]["metrics"]
    metrics_hsl = data_hsl["episodes"][0]["metrics"]
    assert (
        "device_utilization" in metrics_default
    ), "device_utilization must exist in simulated mode (default)"
    assert (
        "device_utilization" in metrics_hsl
    ), "device_utilization must exist in simulated mode (hsl_like)"

    fp_default = data_default.get("policy_fingerprint")
    fp_hsl = data_hsl.get("policy_fingerprint")
    assert (
        fp_default != fp_hsl
    ), "Overlay effect: policy_fingerprint should differ between default and hsl_like"
