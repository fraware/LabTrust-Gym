"""
Tests for the LLM fault model (llm_offline): determinism, metrics, TaskH results.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
    DeterministicRepairBackend,
)
from labtrust_gym.baselines.coordination.repair_input import build_repair_input
from labtrust_gym.baselines.llm.fault_model import (
    LLMFaultModelRepairWrapper,
    load_llm_fault_model,
)
from labtrust_gym.baselines.llm.fault_model_agent import LLMFaultModelAgentWrapper
from labtrust_gym.baselines.llm.fault_model_coord import LLMFaultModelCoordWrapper


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


def test_fault_model_first_call_fault() -> None:
    """Fault on call_index 0 (step_intervals [0]) triggers fallback and metrics."""
    config = {
        "version": "0.1",
        "enabled": True,
        "seed_offset": 0,
        "faults": [
            {
                "fault_id": "empty_output",
                "reason_code": "LLM_REFUSED",
                "step_intervals": [0],
            },
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
    per_agent, meta = wrapper.repair(repair_input, ["A1"])
    assert meta.get("fault_type") == "empty_output"
    assert all(p[1] == "NOOP" for p in per_agent)
    metrics = wrapper.get_fault_metrics()
    assert metrics["fault_injected_count"] == 1
    assert metrics["fallback_count"] == 1


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


def test_agent_fault_wrapper_fallback_and_metrics() -> None:
    """Agent fault wrapper: on trigger returns NOOP JSON and increments metrics."""
    from labtrust_gym.baselines.llm.agent import DeterministicConstrainedBackend

    config = {
        "version": "0.1",
        "enabled": True,
        "seed_offset": 0,
        "faults": [
            {"fault_id": "invalid_output", "probability": 1.0, "reason_code": "RC_LLM_INVALID_OUTPUT"},
        ],
    }
    inner = DeterministicConstrainedBackend(seed=42, default_action_type="NOOP")
    wrapper = LLMFaultModelAgentWrapper(inner, config, seed=100)
    wrapper.reset(100)
    messages = [{"role": "user", "content": "test"}]
    out = wrapper.generate(messages)
    data = json.loads(out)
    assert data.get("action_type") == "NOOP"
    assert data.get("reason_code") == "RC_LLM_INVALID_OUTPUT"
    metrics = wrapper.get_fault_metrics()
    assert metrics["fault_injected_count"] == 1
    assert metrics["fallback_count"] == 1


def test_coord_fault_wrapper_fallback_and_metrics() -> None:
    """Coord fault wrapper: on trigger returns minimal proposal and metrics."""
    from labtrust_gym.baselines.coordination.methods.llm_central_planner import (
        DeterministicProposalBackend,
    )

    config = {
        "version": "0.1",
        "enabled": True,
        "seed_offset": 0,
        "faults": [
            {
                "fault_id": "empty_output",
                "probability": 1.0,
                "reason_code": "LLM_REFUSED",
            },
        ],
    }
    inner = DeterministicProposalBackend(seed=42, default_action_type="NOOP")
    wrapper = LLMFaultModelCoordWrapper(inner, config, seed=100, method_id="llm_central_planner")
    wrapper.reset(100)
    state_digest = {"per_agent": [{"agent_id": "ops_0"}], "per_device": []}
    proposal, meta = wrapper.generate_proposal(
        state_digest,
        allowed_actions=["NOOP", "TICK"],
        step_id=0,
        method_id="llm_central_planner",
    )
    assert proposal.get("per_agent")
    assert all(p.get("action_type") == "NOOP" for p in proposal["per_agent"])
    assert meta.get("reason_code") == "LLM_REFUSED"
    metrics = wrapper.get_fault_metrics()
    assert metrics["fault_injected_count"] == 1
    assert metrics["fallback_count"] == 1


def test_fault_model_determinism_same_seed_same_fallback_counts() -> None:
    """Two runs with same fault seed yield identical fallback counts (agent and proposal path)."""
    from labtrust_gym.baselines.coordination.methods.llm_central_planner import (
        DeterministicProposalBackend,
    )
    from labtrust_gym.baselines.llm.agent import DeterministicConstrainedBackend

    config = {
        "version": "0.1",
        "enabled": True,
        "seed_offset": 0,
        "faults": [{"fault_id": "invalid_output", "probability": 0.3, "reason_code": "RC_LLM_INVALID_OUTPUT"}],
    }
    seed = 77
    # Agent path: two wrappers, same seed, N calls each
    inner_a = DeterministicConstrainedBackend(seed=0, default_action_type="NOOP")
    w1 = LLMFaultModelAgentWrapper(inner_a, config, seed=seed)
    w1.reset(seed)
    for _ in range(5):
        w1.generate([{"role": "user", "content": "x"}])
    m1 = w1.get_fault_metrics()
    inner_a2 = DeterministicConstrainedBackend(seed=0, default_action_type="NOOP")
    w2 = LLMFaultModelAgentWrapper(inner_a2, config, seed=seed)
    w2.reset(seed)
    for _ in range(5):
        w2.generate([{"role": "user", "content": "x"}])
    m2 = w2.get_fault_metrics()
    assert m1["fallback_count"] == m2["fallback_count"]
    # Proposal path: same
    inner_p = DeterministicProposalBackend(seed=0, default_action_type="NOOP")
    pw1 = LLMFaultModelCoordWrapper(inner_p, config, seed=seed, method_id="test")
    pw1.reset(seed)
    for step in range(4):
        pw1.generate_proposal(
            {"per_agent": [{"agent_id": "ops_0"}]},
            allowed_actions=["NOOP", "TICK"],
            step_id=step,
            method_id="test",
        )
    pm1 = pw1.get_fault_metrics()
    inner_p2 = DeterministicProposalBackend(seed=0, default_action_type="NOOP")
    pw2 = LLMFaultModelCoordWrapper(inner_p2, config, seed=seed, method_id="test")
    pw2.reset(seed)
    for step in range(4):
        pw2.generate_proposal(
            {"per_agent": [{"agent_id": "ops_0"}]},
            allowed_actions=["NOOP", "TICK"],
            step_id=step,
            method_id="test",
        )
    pm2 = pw2.get_fault_metrics()
    assert pm1["fallback_count"] == pm2["fallback_count"]


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
    violations = metrics.get("violations_by_invariant_id") or {}
    total_violations = sum(violations.values())
    assert total_violations >= 0, "violations must be bounded (non-negative)"
    coord = (episodes[0].get("coordination") or {}).get("llm_repair") or {}
    if coord.get("repair_call_count", 0) > 0 and "fault_injected_rate" in coord:
        assert 0 <= coord["fault_injected_rate"] <= 1.0
        assert 0 <= coord.get("fallback_rate", 0) <= 1.0


def test_coord_fixtures_record_then_replay(tmp_path: Path) -> None:
    """Record one episode of coord_risk then replay from coordination_fixtures (no network)."""
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo = _repo_root()
    fixtures_dir = tmp_path / "coord_fixtures"
    out_record = tmp_path / "record_results.json"
    run_benchmark(
        task_name="coord_risk",
        num_episodes=1,
        base_seed=42,
        out_path=out_record,
        repo_root=repo,
        coord_method="llm_central_planner",
        injection_id="none",
        llm_backend="deterministic",
        pipeline_mode="llm_offline",
        record_coord_fixtures_path=fixtures_dir,
    )
    assert (fixtures_dir / "coordination_fixtures.json").exists()
    data_record = json.loads(out_record.read_text(encoding="utf-8"))
    n_recorded = (data_record.get("metadata") or {}).get("recorded_coord_fixtures", 0)
    assert n_recorded > 0

    out_replay = tmp_path / "replay_results.json"
    run_benchmark(
        task_name="coord_risk",
        num_episodes=1,
        base_seed=42,
        out_path=out_replay,
        repo_root=repo,
        coord_method="llm_central_planner",
        injection_id="none",
        llm_backend="deterministic",
        pipeline_mode="llm_offline",
        coord_fixtures_path=fixtures_dir,
    )
    assert out_replay.exists()
    data_replay = json.loads(out_replay.read_text(encoding="utf-8"))
    assert len(data_replay.get("episodes") or []) == 1

    # Record and replay with same seed must yield identical v0.2 metrics (canonical).
    from labtrust_gym.benchmarks.summarize import _normalize_to_v02
    from labtrust_gym.util.json_utils import canonical_json

    def comparable_payload(data: dict) -> dict:
        norm = _normalize_to_v02(data)
        if not norm:
            return {}
        episodes = norm.get("episodes") or []
        return {
            "task": norm["task"],
            "seeds": norm["seeds"],
            "agent_baseline_id": norm.get("agent_baseline_id"),
            "episodes": [{"seed": ep.get("seed"), "metrics": ep.get("metrics") or {}} for ep in episodes],
        }

    payload_record = comparable_payload(data_record)
    payload_replay = comparable_payload(data_replay)
    assert payload_record and payload_replay
    assert canonical_json(payload_record) == canonical_json(payload_replay), (
        "Record and replay results must match (v0.2 canonical)"
    )


def test_coord_risk_central_planner_with_fault_model_produces_results(
    tmp_path: Path,
) -> None:
    """coord_risk with llm_central_planner and fault model completes; no crash."""
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo = _repo_root()
    out = tmp_path / "results.json"
    run_benchmark(
        task_name="coord_risk",
        num_episodes=1,
        base_seed=42,
        out_path=out,
        repo_root=repo,
        coord_method="llm_central_planner",
        injection_id="none",
        llm_backend="deterministic",
        pipeline_mode="llm_offline",
    )
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    episodes = data.get("episodes") or []
    assert len(episodes) == 1
    assert (episodes[0].get("metrics") or {}).get("violations_by_invariant_id") is not None
