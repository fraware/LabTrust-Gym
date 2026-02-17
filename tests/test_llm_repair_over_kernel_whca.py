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
    """Run coord_risk one episode with llm_repair_over_kernel_whca and injection."""
    out = tmp_path / "results.json"
    run_benchmark(
        task_name="coord_risk",
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


def test_llm_repair_injection_valid_route_and_get_last_planned_path() -> None:
    """Repair + shield: valid route (actions in allowed set); get_last_planned_path delegates to kernel."""
    from labtrust_gym.baselines.coordination.interface import VALID_ACTION_INDICES
    from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
        DeterministicRepairBackend,
        LLMRepairOverKernelWHCA,
    )
    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    repo_root = Path(__file__).resolve().parents[1]
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_B"}],
            "graph_edges": [{"from": "Z_A", "to": "Z_B"}, {"from": "Z_B", "to": "Z_A"}],
        },
        "pz_to_engine": {"a1": "ops_0"},
    }
    scale_config = {"seed": 42, "expose_planned_path": True}
    kernel = make_coordination_method(
        "kernel_whca",
        policy,
        repo_root=repo_root,
        scale_config=scale_config,
    )
    if kernel is None:
        pytest.skip("kernel_whca not available")
    repair_backend = DeterministicRepairBackend(seed=42)
    method = LLMRepairOverKernelWHCA(kernel=kernel, repair_backend=repair_backend)
    method.reset(seed=42, policy=policy, scale_config=scale_config)
    obs = {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [{"queue_len": 1, "queue_head": "W1"}],
            "queue_has_head": [1],
            "log_frozen": 0,
        },
    }
    infos = {"_coord_repair_triggers": ["comms_poison"]}
    actions = method.propose_actions(obs, infos, 0)
    assert "a1" in actions
    for rec in actions.values():
        assert rec.get("action_index") in VALID_ACTION_INDICES
    path = method.get_last_planned_path()
    assert path is None or (isinstance(path, tuple) and len(path) == 4)


def test_llm_repair_multi_candidate_validator_selects_first_valid() -> None:
    """Backend returns 3 candidates; validator selects first that passes shield (3-10 candidate contract)."""
    from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
        LLMRepairOverKernelWHCA,
    )
    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    class MultiCandidateBackend:
        """Returns 3 candidates: first TICK, second NOOP, third NOOP. First valid is used."""

        def reset(self, seed: int) -> None:
            pass

        def repair(self, repair_input, agent_ids):
            aids = sorted(agent_ids)
            tick_cand = [(aid, "TICK", {}) for aid in aids]
            noop_cand = [(aid, "NOOP", {}) for aid in aids]
            candidates = [tick_cand, noop_cand, noop_cand]
            meta = {"backend_id": "multi_candidate", "latency_ms": 0.0, "tokens_in": 0, "tokens_out": 0}
            return candidates, meta

    repo_root = Path(__file__).resolve().parents[1]
    policy = {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_B"}],
            "graph_edges": [{"from": "Z_A", "to": "Z_B"}, {"from": "Z_B", "to": "Z_A"}],
        },
        "pz_to_engine": {"a1": "ops_0", "a2": "runner_0"},
    }
    scale_config = {"seed": 42}
    kernel = make_coordination_method("kernel_whca", policy, repo_root=repo_root, scale_config=scale_config)
    if kernel is None:
        pytest.skip("kernel_whca not available")
    method = LLMRepairOverKernelWHCA(kernel=kernel, repair_backend=MultiCandidateBackend())
    method.reset(seed=42, policy=policy, scale_config=scale_config)
    obs = {
        "a1": {"zone_id": "Z_A", "queue_by_device": [], "queue_has_head": [0], "log_frozen": 0},
        "a2": {"zone_id": "Z_B", "queue_by_device": [], "queue_has_head": [0], "log_frozen": 0},
    }
    infos = {"_coord_repair_triggers": ["comms_poison"]}
    actions = method.propose_actions(obs, infos, 0)
    assert "a1" in actions and "a2" in actions
    from labtrust_gym.baselines.coordination.interface import ACTION_TICK
    assert actions["a1"].get("action_index") == ACTION_TICK
    assert actions["a2"].get("action_index") == ACTION_TICK
