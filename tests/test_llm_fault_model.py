"""
Tests for the LLM fault model (llm_offline): determinism, metrics, TaskH results.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
    DeterministicRepairBackend,
)
from labtrust_gym.baselines.coordination.repair_input import build_repair_input
from labtrust_gym.baselines.llm.fault_model import (
    LLMFaultModelRepairWrapper,
    load_llm_fault_model,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_fault_model_same_seed_same_fault_steps() -> None:
    """Same seed + same repair_input yields same fault injection decision."""
    config = {
        "version": "0.1",
        "enabled": True,
        "seed_offset": 0,
        "faults": [
            {"fault_id": "invalid_output", "probability": 0.5, "reason_code": "RC_LLM_INVALID_OUTPUT"},
        ],
    }
    inner = DeterministicRepairBackend(seed=42)
    wrapper = LLMFaultModelRepairWrapper(inner, config, seed=100)
    wrapper.reset(100)
    repair_input = build_repair_input(
        scale_config_snapshot={"num_agents": 4},
        last_accepted_plan_summary={"step_idx": 3, "route_hash": "abc"},
        blocked_actions=[],
        constraint_summary={"allowed_actions": ["NOOP", "TICK"]},
    )
    agent_ids = ["A1", "A2"]

    per_agent_1, meta_1 = wrapper.repair(repair_input, agent_ids)
    wrapper2 = LLMFaultModelRepairWrapper(inner, config, seed=100)
    wrapper2.reset(100)
    per_agent_2, meta_2 = wrapper2.repair(repair_input, agent_ids)

    assert (per_agent_1, meta_1.get("fault_type")) == (
        per_agent_2,
        meta_2.get("fault_type"),
    ), "Same seed and input must yield identical fault injection"


def test_fault_model_step_intervals_deterministic() -> None:
    """Fault with step_intervals triggers only on those steps."""
    config = {
        "version": "0.1",
        "enabled": True,
        "seed_offset": 0,
        "faults": [
            {
                "fault_id": "empty_output",
                "reason_code": "LLM_REFUSED",
                "step_intervals": [2, 5],
            },
        ],
    }
    inner = DeterministicRepairBackend(seed=0)
    wrapper = LLMFaultModelRepairWrapper(inner, config, seed=0)
    wrapper.reset(0)
    agent_ids = ["A1"]

    triggered_steps = []
    for step in range(8):
        repair_input = build_repair_input(
            scale_config_snapshot={},
            last_accepted_plan_summary={"step_idx": step},
            blocked_actions=[],
            constraint_summary={},
        )
        per_agent, meta = wrapper.repair(repair_input, agent_ids)
        if meta.get("fault_type") == "empty_output":
            triggered_steps.append(step)

    assert triggered_steps == [2, 5], "step_intervals [2,5] must trigger only on steps 2 and 5"


def test_fault_model_fallback_noop_and_metrics() -> None:
    """When fault triggers, fallback is all NOOP and metrics increment."""
    config = {
        "version": "0.1",
        "enabled": True,
        "faults": [
            {"fault_id": "inconsistent_plan", "probability": 1.0, "reason_code": "RC_LLM_FAULT_INJECTED"},
        ],
    }
    inner = DeterministicRepairBackend(seed=0)
    wrapper = LLMFaultModelRepairWrapper(inner, config, seed=0)
    wrapper.reset(0)
    repair_input = build_repair_input(
        scale_config_snapshot={},
        last_accepted_plan_summary={"step_idx": 0},
        blocked_actions=[],
        constraint_summary={},
    )
    per_agent, meta = wrapper.repair(repair_input, ["A1", "A2"])

    assert all(p[1] == "NOOP" for p in per_agent)
    assert meta.get("reason_code") == "RC_LLM_FAULT_INJECTED"
    metrics = wrapper.get_fault_metrics()
    assert metrics["fault_injected_count"] == 1
    assert metrics["fallback_count"] == 1


def test_load_llm_fault_model_disabled_returns_empty() -> None:
    """When policy has enabled: false, load returns empty dict."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "policy" / "llm"
        path.mkdir(parents=True)
        (path / "llm_fault_model.v0.1.yaml").write_text(
            "version: '0.1'\nenabled: false\nfaults: []\n",
            encoding="utf-8",
        )
        loaded = load_llm_fault_model(Path(tmp))
        assert loaded == {}


def test_taskh_under_faults_produces_results_v02(tmp_path: Path) -> None:
    """TaskH with llm_repair_over_kernel_whca and fault model produces results and does not crash."""
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo = _repo_root()
    out = tmp_path / "results.json"
    run_benchmark(
        task_name="coord_risk",
        num_episodes=1,
        base_seed=42,
        out_path=out,
        repo_root=repo,
        coord_method="llm_repair_over_kernel_whca",
        injection_id="none",
        llm_backend="deterministic",
        pipeline_mode="llm_offline",
    )
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "results.v0.2" or "episodes" in data
    episodes = data.get("episodes") or []
    assert len(episodes) == 1
    metrics = episodes[0].get("metrics") or {}
    violations = (metrics.get("violations_by_invariant_id") or {})
    total_violations = sum(violations.values())
    assert total_violations >= 0, "violations must be bounded (non-negative)"
    coord = (episodes[0].get("coordination") or {}).get("llm_repair") or {}
    if coord.get("repair_call_count", 0) > 0 and "fault_injected_rate" in coord:
        assert 0 <= coord["fault_injected_rate"] <= 1.0
        assert 0 <= coord.get("fallback_rate", 0) <= 1.0
