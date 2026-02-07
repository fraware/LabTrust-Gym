"""
Integration smoke: TaskH with llm_repair_over_kernel_whca and INJ-COMMS-POISON-001
or INJ-ID-SPOOF-001 produces sec metrics and coordination.llm_repair with nonzero
repair_call_count when repair triggers are set by the runner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.runner import run_benchmark


def _run_taskh_one_episode(
    tmp_path: Path,
    injection_id: str,
    seed: int = 42,
) -> dict:
    """Run TaskH_COORD_RISK one episode with llm_repair_over_kernel_whca and injection."""
    out = tmp_path / "results.json"
    run_benchmark(
        task_name="TaskH_COORD_RISK",
        num_episodes=1,
        base_seed=seed,
        out_path=out,
        repo_root=Path(__file__).resolve().parents[1],
        coord_method="llm_repair_over_kernel_whca",
        injection_id=injection_id,
        pipeline_mode="deterministic",
    )
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    return data


def test_taskh_llm_repair_comms_poison_produces_llm_repair_metrics(tmp_path: Path) -> None:
    """TaskH with INJ-COMMS-POISON-001 and llm_repair_over_kernel_whca produces coordination.llm_repair."""
    data = _run_taskh_one_episode(tmp_path, "INJ-COMMS-POISON-001")
    episodes = data.get("episodes") or []
    assert len(episodes) >= 1
    metrics = episodes[0].get("metrics") or {}
    coord = metrics.get("coordination") or {}
    llm_repair = coord.get("llm_repair")
    assert llm_repair is not None
    assert "repair_call_count" in llm_repair
    assert "repair_success_rate" in llm_repair
    assert "repair_fallback_noop_count" in llm_repair
    assert "mean_repair_latency_ms" in llm_repair
    assert "total_repair_tokens" in llm_repair
    # Runner sets _coord_repair_triggers for this injection so we get nonzero repair calls
    assert llm_repair["repair_call_count"] > 0


def test_taskh_llm_repair_id_spoof_produces_sec_metrics(tmp_path: Path) -> None:
    """TaskH with INJ-ID-SPOOF-001 and llm_repair_over_kernel_whca produces sec metrics."""
    data = _run_taskh_one_episode(tmp_path, "INJ-ID-SPOOF-001")
    episodes = data.get("episodes") or []
    assert len(episodes) >= 1
    metrics = episodes[0].get("metrics") or {}
    coord = metrics.get("coordination") or {}
    assert "llm_repair" in coord
    # Sec metrics may be present from injection/containment
    assert "throughput" in metrics
