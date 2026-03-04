"""
Deterministic track tests for group_evolving_experience_sharing.

Ensures the experience-sharing variant is stable and CI-safe: same seed yields
identical behavior (e.g. same actions over a short run).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_group_evolving_experience_sharing_deterministic_same_seed(tmp_path: Path) -> None:
    """Same seed -> identical metrics (throughput, steps) and coordination behavior."""
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    run_benchmark(
        task_name="coord_scale",
        num_episodes=1,
        base_seed=42,
        out_path=out1,
        repo_root=_repo_root(),
        coord_method="group_evolving_experience_sharing",
        pipeline_mode="deterministic",
    )
    run_benchmark(
        task_name="coord_scale",
        num_episodes=1,
        base_seed=42,
        out_path=out2,
        repo_root=_repo_root(),
        coord_method="group_evolving_experience_sharing",
        pipeline_mode="deterministic",
    )
    d1 = json.loads(out1.read_text(encoding="utf-8"))
    d2 = json.loads(out2.read_text(encoding="utf-8"))
    eps1 = d1.get("episodes") or []
    eps2 = d2.get("episodes") or []
    assert len(eps1) == 1 and len(eps2) == 1
    m1 = eps1[0].get("metrics") or {}
    m2 = eps2[0].get("metrics") or {}
    assert m1.get("throughput") == m2.get("throughput")
    assert m1.get("steps") == m2.get("steps")


def test_group_evolving_experience_sharing_injection_comms_poison_no_crash(tmp_path: Path) -> None:
    """coord_risk with group_evolving_experience_sharing and INJ-COMMS-POISON-001: no crash, metrics present."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    out = tmp_path / "coord_risk_out.json"
    run_benchmark(
        task_name="coord_risk",
        num_episodes=1,
        base_seed=42,
        out_path=out,
        repo_root=_repo_root(),
        coord_method="group_evolving_experience_sharing",
        injection_id="INJ-COMMS-POISON-001",
        pipeline_mode="deterministic",
    )
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    episodes = data.get("episodes") or []
    assert len(episodes) >= 1
    metrics = episodes[0].get("metrics") or {}
    assert "throughput" in metrics or "coordination" in metrics


def test_group_evolving_experience_sharing_contract_five_steps(tmp_path: Path) -> None:
    """Experience sharing method runs 5 steps without error and returns valid actions."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from dataclasses import asdict

    from labtrust_gym.baselines.coordination.interface import (
        VALID_ACTION_INDICES,
        action_dict_to_index_and_info,
    )
    from labtrust_gym.baselines.coordination.registry import make_coordination_method
    from labtrust_gym.benchmarks.coordination_scale import (
        CoordinationScaleConfig,
        generate_scaled_initial_state,
    )
    from labtrust_gym.benchmarks.tasks import get_task

    repo_root = _repo_root()
    scale_config = CoordinationScaleConfig(
        num_agents_total=3,
        role_mix={"ROLE_RUNNER": 0.6, "ROLE_ANALYTICS": 0.3, "ROLE_RECEPTION": 0.1},
        num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=1.0,
        horizon_steps=10,
        timing_mode="explicit",
        partner_id=None,
    )
    scale_probe = generate_scaled_initial_state(scale_config, repo_root, 42)
    scale_dict = asdict(scale_config)
    scale_dict["seed"] = 42
    policy = (scale_probe.get("effective_policy") or {}).copy()
    agents = scale_probe.get("agents") or []
    policy["pz_to_engine"] = {f"worker_{i}": a["agent_id"] for i, a in enumerate(agents)}
    method = make_coordination_method(
        "group_evolving_experience_sharing",
        policy,
        repo_root=repo_root,
        scale_config=scale_dict,
    )
    task = get_task("coord_scale")
    task.max_steps = 5
    initial_state = task.get_initial_state(42)
    initial_state["effective_policy"] = scale_probe.get("effective_policy")
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    env = LabTrustParallelEnv(
        num_runners=0,
        num_adversaries=0,
        num_insiders=0,
        dt_s=10,
        reward_config=task.reward_config or {},
        policy_dir=repo_root / "policy",
        scale_agents=agents,
        scale_device_ids=scale_probe.get("_scale_device_ids") or [],
        scale_zone_ids=scale_probe.get("_scale_zone_ids") or [],
    )
    obs, _ = env.reset(seed=42, options={"initial_state": initial_state})
    method.reset(42, initial_state.get("effective_policy") or {}, scale_dict)
    for t in range(5):
        actions_dict = method.propose_actions(obs, {}, t)
        assert isinstance(actions_dict, dict)
        for agent_id in env.agents:
            ad = actions_dict.get(agent_id, {"action_index": 0})
            idx = ad["action_index"]
            assert idx in VALID_ACTION_INDICES
        actions = {a: action_dict_to_index_and_info(actions_dict.get(a, {"action_index": 0}))[0] for a in env.agents}
        action_infos = {
            a: action_dict_to_index_and_info(actions_dict.get(a, {"action_index": 0}))[1] for a in env.agents
        }
        obs, _, _, _, infos = env.step(actions, action_infos=action_infos)
        if hasattr(method, "on_step_result") and infos:
            first_agent = next(iter(env.agents), None)
            step_results = (infos.get(first_agent) or {}).get("_benchmark_step_results", [])
            method.on_step_result(step_results)
    env.close()
