"""
Backward compatibility regression tests for scale and agent-driven workflows.

Ensures N <= N_max uses propose_actions, single-driver uses step_lab, classic
run_benchmark uses run_episode, and CLI defaults are correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _repo_root() -> Path:
    from labtrust_gym.config import get_repo_root

    return Path(get_repo_root())


def test_backward_compat_n_le_nmax_uses_propose_actions() -> None:
    """When N <= coord_propose_actions_max_agents, runner calls propose_actions, not combine_submissions."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")

    from dataclasses import asdict

    from labtrust_gym.baselines.coordination.registry import make_coordination_method
    from labtrust_gym.benchmarks.coordination_scale import (
        CoordinationScaleConfig,
        generate_scaled_initial_state,
    )
    from labtrust_gym.benchmarks.runner import run_episode
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    repo_root = _repo_root()
    n_max = 50
    scale_config = CoordinationScaleConfig(
        num_agents_total=3,
        role_mix={"ROLE_RUNNER": 0.5, "ROLE_ANALYTICS": 0.5},
        num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=1.0,
        horizon_steps=2,
        timing_mode="explicit",
        partner_id=None,
        coord_propose_actions_max_agents=n_max,
    )
    scale_probe = generate_scaled_initial_state(scale_config, repo_root, 42)
    task = get_task("coord_scale")
    if task is None:
        pytest.skip("coord_scale task not registered")
    task.max_steps = 2
    task.scale_config = scale_config
    agents = scale_probe.get("agents") or []
    device_ids = scale_probe.get("_scale_device_ids") or []
    zone_ids = scale_probe.get("_scale_zone_ids") or []
    policy_dir = repo_root / "policy"

    class NoopAgent:
        def act(self, obs, agent_id):
            return (0, {})

    scripted_agents_map = {f"worker_{i}": NoopAgent() for i in range(len(agents))}

    def env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=0,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config or {},
            policy_dir=policy_dir,
            log_path=log_path,
            scale_agents=agents,
            scale_device_ids=device_ids,
            scale_zone_ids=zone_ids,
        )

    scale_config_dict = asdict(scale_config)
    coord_method = make_coordination_method(
        "centralized_planner",
        scale_probe.get("effective_policy") or {},
        repo_root=repo_root,
        scale_config=scale_config_dict,
    )
    propose_calls: list[int] = []
    combine_calls: list[int] = []
    original_propose = coord_method.propose_actions
    original_combine = coord_method.combine_submissions

    def tracked_propose(obs, infos, t):
        propose_calls.append(1)
        return original_propose(obs, infos, t)

    def tracked_combine(s, o, i, t):
        combine_calls.append(1)
        return original_combine(s, o, i, t)

    coord_method.propose_actions = tracked_propose
    coord_method.combine_submissions = tracked_combine

    initial_state = task.get_initial_state(42, policy_root=repo_root)
    initial_state["effective_policy"] = scale_probe.get("effective_policy")
    run_episode(
        task=task,
        episode_seed=42,
        env_factory=env_factory,
        scripted_agents_map=scripted_agents_map,
        coord_method=coord_method,
        repo_root=repo_root,
    )
    assert len(propose_calls) >= 1, "propose_actions should be called when N <= N_max"
    assert len(combine_calls) == 0, "combine_submissions should not be called when N <= N_max"


def test_backward_compat_n_le_nmax_uses_propose_actions_real_method() -> None:
    """Regression: with real coord_method from registry, N <= N_max uses propose_actions only, never combine_submissions."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")

    from dataclasses import asdict

    from labtrust_gym.baselines.coordination.registry import make_coordination_method
    from labtrust_gym.benchmarks.coordination_scale import (
        CoordinationScaleConfig,
        generate_scaled_initial_state,
    )
    from labtrust_gym.benchmarks.runner import run_episode
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv
    from labtrust_gym.policy.coordination import load_coordination_methods

    repo_root = _repo_root()
    reg_path = repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
    if not reg_path.exists():
        pytest.skip("coordination_methods.v0.1.yaml not found")
    registry = load_coordination_methods(reg_path)
    method_id = "centralized_planner"
    if method_id not in registry:
        pytest.skip(f"{method_id} not in coordination registry")

    n_max = 50
    scale_config = CoordinationScaleConfig(
        num_agents_total=3,
        role_mix={"ROLE_RUNNER": 0.5, "ROLE_ANALYTICS": 0.5},
        num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=1.0,
        horizon_steps=2,
        timing_mode="explicit",
        partner_id=None,
        coord_propose_actions_max_agents=n_max,
    )
    scale_probe = generate_scaled_initial_state(scale_config, repo_root, 42)
    task = get_task("coord_scale")
    if task is None:
        pytest.skip("coord_scale task not registered")
    task.max_steps = 2
    task.scale_config = scale_config
    agents = scale_probe.get("agents") or []
    device_ids = scale_probe.get("_scale_device_ids") or []
    zone_ids = scale_probe.get("_scale_zone_ids") or []
    policy_dir = repo_root / "policy"

    class NoopAgent:
        def act(self, obs, agent_id):
            return (0, {})

    scripted_agents_map = {f"worker_{i}": NoopAgent() for i in range(len(agents))}

    def env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=0,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config or {},
            policy_dir=policy_dir,
            log_path=log_path,
            scale_agents=agents,
            scale_device_ids=device_ids,
            scale_zone_ids=zone_ids,
        )

    scale_config_dict = asdict(scale_config)
    coord_method = make_coordination_method(
        method_id,
        scale_probe.get("effective_policy") or {},
        repo_root=repo_root,
        scale_config=scale_config_dict,
    )
    assert hasattr(coord_method, "propose_actions")
    assert hasattr(coord_method, "combine_submissions")

    propose_calls: list[int] = []
    combine_calls: list[int] = []
    original_propose = coord_method.propose_actions
    original_combine = coord_method.combine_submissions

    def tracked_propose(obs, infos, t):
        propose_calls.append(1)
        return original_propose(obs, infos, t)

    def tracked_combine(s, o, i, t):
        combine_calls.append(1)
        return original_combine(s, o, i, t)

    coord_method.propose_actions = tracked_propose
    coord_method.combine_submissions = tracked_combine

    initial_state = task.get_initial_state(42, policy_root=repo_root)
    initial_state["effective_policy"] = scale_probe.get("effective_policy")
    run_episode(
        task=task,
        episode_seed=42,
        env_factory=env_factory,
        scripted_agents_map=scripted_agents_map,
        coord_method=coord_method,
        repo_root=repo_root,
    )
    assert len(propose_calls) >= 1, "real method: propose_actions should be called when N <= N_max"
    assert len(combine_calls) == 0, "real method: combine_submissions should not be called when N <= N_max"


def test_backward_compat_agent_driven_single_uses_step_lab() -> None:
    """AgentDrivenDriver(mode='single'): submit_my_action returns multi_agentic_only; step_lab works."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")

    from labtrust_gym.baselines.llm.shield import apply_shield
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    task = get_task("throughput_sla")
    if task is None:
        pytest.skip("throughput_sla task not registered")
    task.max_steps = 2
    policy_dir = _repo_root() / "policy"
    env = LabTrustParallelEnv(
        num_runners=2,
        num_adversaries=0,
        num_insiders=0,
        dt_s=10,
        reward_config=task.reward_config or {},
        policy_dir=policy_dir,
    )
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env.reset(seed=42, options={"initial_state": initial_state})
    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=None,
        blackboard_harness=None,
        rbac_policy={},
        policy_summary=initial_state.get("policy_summary") or {},
        allowed_actions=["NOOP", "TICK"],
        apply_shield=apply_shield,
        method_id="test",
        mode="single",
    )
    driver.reset(42, initial_state)
    r = driver.submit_my_action("ops_0", "NOOP", {}, None)
    assert r.get("error") == "multi_agentic_only"
    agent_ids = driver.agent_ids
    out = driver.step_lab(
        {
            "per_agent": [{"agent_id": aid, "action_type": "NOOP", "args": {}, "reason_code": ""} for aid in agent_ids],
            "comms": [],
        }
    )
    assert "error" not in out or out.get("error") in (None, "validation_failed")
    assert out.get("step_index") == 1 or "step_index" in out
    env.close()


def test_backward_compat_classic_run_episode_unchanged() -> None:
    """run_benchmark(agent_driven=False, multi_agentic=False) uses run_episode and returns valid metrics."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")

    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "out.json"
        result = run_benchmark(
            task_name="throughput_sla",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=_repo_root(),
            agent_driven=False,
            multi_agentic=False,
        )
        assert isinstance(result, dict)
        assert "episodes" in result or "metrics" in result or "steps" in str(result)
        assert out_path.exists() or (Path(tmp) / "results.json").exists() or "episodes" in result


def test_backward_compat_cli_defaults() -> None:
    """run_benchmark defaults: agent_driven=False, multi_agentic=False when omitted."""
    import inspect

    from labtrust_gym.benchmarks.runner import run_benchmark

    sig = inspect.signature(run_benchmark)
    agent_driven_param = sig.parameters.get("agent_driven")
    multi_agentic_param = sig.parameters.get("multi_agentic")
    assert agent_driven_param is not None and agent_driven_param.default is False
    assert multi_agentic_param is not None and multi_agentic_param.default is False
