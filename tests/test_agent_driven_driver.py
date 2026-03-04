"""
Tests for agent-driven episode driver and run_episode_agent_driven.

Uses DeterministicAgentDrivenBackend (no LLM) to run one episode; validates
step count and metrics shape match expectations. Does not modify run_episode or runner loop.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.agent_driven_driver import (
    SUBMIT_MY_ACTION_TOOL_NAME,
    DeterministicAgentDrivenBackend,
    ParallelMultiAgenticBackend,
    agent_driven_tool_definitions,
    run_episode_agent_driven,
    step_lab_tool_schema,
    submit_my_action_tool_schema,
)
from labtrust_gym.benchmarks.tasks import get_task


def _repo_root() -> Path:
    from labtrust_gym.config import get_repo_root

    return Path(get_repo_root())


@pytest.fixture(scope="module")
def _task_and_env_factory():
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    task = get_task("throughput_sla")
    if task is None:
        pytest.skip("throughput_sla task not registered")
    task.max_steps = 5
    policy_dir = _repo_root() / "policy"
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    def env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=2,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config,
            policy_dir=policy_dir,
            log_path=log_path,
        )

    return task, env_factory


def test_agent_driven_driver_step_lab_once(_task_and_env_factory) -> None:
    """Single step_lab call returns step_index 1 and no error (smoke)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.llm.shield import apply_shield
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver

    task, env_factory = _task_and_env_factory
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env = env_factory(initial_state=initial_state, reward_config=task.reward_config, log_path=None)
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
    )
    driver.reset(42, initial_state)
    agent_ids = driver.agent_ids
    assert len(agent_ids) > 0, "env.agents should be non-empty after reset"
    noop_proposal = {
        "per_agent": [{"agent_id": aid, "action_type": "NOOP", "args": {}, "reason_code": None} for aid in agent_ids],
        "comms": [],
    }
    out = driver.step_lab(noop_proposal)
    assert "error" not in out or out.get("error") is None, f"step_lab should not return error: {out}"
    assert out.get("step_index") == 1, f"expected step_index 1: {out}"
    assert len(driver.step_results_per_step) == 1
    env.close()


def test_agent_driven_tool_schema() -> None:
    """Tool definitions for step_lab and optional tools are non-empty and have expected names."""
    tools = agent_driven_tool_definitions(include_optional=True)
    assert len(tools) >= 1
    names = [t.get("function", {}).get("name") for t in tools if isinstance(t, dict)]
    assert "step_lab" in names
    tools_multi = agent_driven_tool_definitions(include_optional=True, multi_agentic=True)
    names_multi = [t.get("function", {}).get("name") for t in tools_multi if isinstance(t, dict)]
    assert SUBMIT_MY_ACTION_TOOL_NAME in names_multi
    assert "step_lab" not in names_multi
    step_lab = step_lab_tool_schema()
    assert step_lab.get("function", {}).get("name") == "step_lab"
    assert "parameters" in step_lab.get("function", {})
    submit_tool = submit_my_action_tool_schema()
    assert submit_tool.get("function", {}).get("name") == SUBMIT_MY_ACTION_TOOL_NAME


def test_agent_driven_driver_multi_agentic_submit_and_advance(_task_and_env_factory) -> None:
    """Multi-agentic mode: submit_my_action per agent then try_advance_step runs combine and env.step."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )
    from labtrust_gym.baselines.llm.shield import apply_shield
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver

    task, env_factory = _task_and_env_factory
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env = env_factory(initial_state=initial_state, reward_config=task.reward_config, log_path=None)
    env.reset(seed=42, options={"initial_state": initial_state})
    coord_method = CentralizedPlanner()
    coord_method.reset(42, initial_state.get("effective_policy") or {}, {})
    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=None,
        blackboard_harness=None,
        rbac_policy={},
        policy_summary=initial_state.get("policy_summary") or {},
        allowed_actions=["NOOP", "TICK"],
        apply_shield=apply_shield,
        method_id="test_multi",
        mode="multi_agentic",
        coord_method=coord_method,
    )
    driver.reset(42, initial_state)
    agent_ids = driver.agent_ids
    assert len(agent_ids) >= 1
    for aid in agent_ids:
        r = driver.submit_my_action(aid, "NOOP", {}, None)
        assert r.get("received") is True, r
    out = driver.try_advance_step(force=False)
    assert out.get("stepped") is True, out
    assert "result" in out
    assert out["result"].get("step_index") == 1
    assert out["result"].get("done") is False or task.max_steps <= 1
    env.close()


def test_agent_driven_multi_agentic_auction_submit_bid(_task_and_env_factory) -> None:
    """Multi-agentic with market_auction: submit_bid per agent, try_advance_step runs combine."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.coordination.methods.market_auction import (
        MarketAuction,
    )
    from labtrust_gym.baselines.llm.shield import apply_shield
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver

    task, env_factory = _task_and_env_factory
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env = env_factory(initial_state=initial_state, reward_config=task.reward_config, log_path=None)
    env.reset(seed=42, options={"initial_state": initial_state})
    coord_method = MarketAuction(collusion=False)
    coord_method.reset(42, initial_state.get("effective_policy") or {}, {})
    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=None,
        blackboard_harness=None,
        rbac_policy={},
        policy_summary=initial_state.get("policy_summary") or {},
        allowed_actions=["NOOP", "TICK"],
        apply_shield=apply_shield,
        method_id="test_auction",
        mode="multi_agentic",
        coord_method=coord_method,
    )
    driver.reset(42, initial_state)
    agent_ids = driver.agent_ids
    assert len(agent_ids) >= 1
    for aid in agent_ids:
        r = driver.submit_bid(aid, {"cost": 0, "device_id": "d0", "work_id": "W", "zone_id": "Z1"})
        assert r.get("received") is True, r
    out = driver.try_advance_step(force=False)
    assert out.get("stepped") is True, out
    assert "result" in out
    assert "observations" in out["result"]
    assert out["result"].get("step_index") == 1
    env.close()


def test_parallel_multi_agentic_backend_noop(_task_and_env_factory) -> None:
    """ParallelMultiAgenticBackend with NOOP factory: 5 agents, verify step count and metrics."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )
    from labtrust_gym.baselines.llm.shield import apply_shield
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver

    task, env_factory = _task_and_env_factory
    task.max_steps = 3
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env = env_factory(initial_state=initial_state, reward_config=task.reward_config, log_path=None)
    env.reset(seed=42, options={"initial_state": initial_state})
    coord_method = CentralizedPlanner()
    coord_method.reset(42, initial_state.get("effective_policy") or {}, {})
    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=None,
        blackboard_harness=None,
        rbac_policy={},
        policy_summary=initial_state.get("policy_summary") or {},
        allowed_actions=["NOOP", "TICK"],
        apply_shield=apply_shield,
        method_id="test_parallel",
        mode="multi_agentic",
        coord_method=coord_method,
    )
    driver.reset(42, initial_state)
    agent_ids = driver.agent_ids
    assert len(agent_ids) >= 1

    def noop_runner(aid: str):
        def _run(d: AgentDrivenDriver, _agent_id: str) -> None:
            d.submit_my_action(_agent_id, "NOOP", {}, None)

        return _run

    backend = ParallelMultiAgenticBackend(
        agent_backend_factory=noop_runner,
        max_workers=8,
        round_timeout_s=10.0,
        max_steps_to_run=3,
    )
    backend.run_episode(driver)
    assert driver._step_index == 3
    assert len(driver.step_results_per_step) == 3
    env.close()


def test_parallel_timeout_fills_noop(_task_and_env_factory) -> None:
    """Parallel backend: one agent sleeps 2s, timeout 0.3s; force advance fills missing with NOOP."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )
    from labtrust_gym.baselines.llm.shield import apply_shield
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver

    task, env_factory = _task_and_env_factory
    task.max_steps = 2
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env = env_factory(initial_state=initial_state, reward_config=task.reward_config, log_path=None)
    env.reset(seed=42, options={"initial_state": initial_state})
    coord_method = CentralizedPlanner()
    coord_method.reset(42, initial_state.get("effective_policy") or {}, {})
    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=None,
        blackboard_harness=None,
        rbac_policy={},
        policy_summary=initial_state.get("policy_summary") or {},
        allowed_actions=["NOOP", "TICK"],
        apply_shield=apply_shield,
        method_id="test_timeout",
        mode="multi_agentic",
        coord_method=coord_method,
    )
    driver.reset(42, initial_state)
    agent_ids = driver.agent_ids
    first_agent = agent_ids[0]

    def slow_first_agent(aid: str):
        def _run(d: AgentDrivenDriver, _agent_id: str) -> None:
            if _agent_id == first_agent:
                time.sleep(2.0)
            d.submit_my_action(_agent_id, "NOOP", {}, None)

        return _run

    backend = ParallelMultiAgenticBackend(
        agent_backend_factory=slow_first_agent,
        max_workers=8,
        round_timeout_s=0.3,
        max_steps_to_run=2,
    )
    backend.run_episode(driver)
    assert driver._step_index == 2
    assert len(driver.step_results_per_step) == 2
    env.close()


def test_thread_safe_submissions(_task_and_env_factory) -> None:
    """Concurrent submit_my_action from 10 threads; no KeyError or data corruption."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )
    from labtrust_gym.baselines.llm.shield import apply_shield
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver

    task, env_factory = _task_and_env_factory
    task.max_steps = 1
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env = env_factory(initial_state=initial_state, reward_config=task.reward_config, log_path=None)
    env.reset(seed=42, options={"initial_state": initial_state})
    coord_method = CentralizedPlanner()
    coord_method.reset(42, initial_state.get("effective_policy") or {}, {})
    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=None,
        blackboard_harness=None,
        rbac_policy={},
        policy_summary=initial_state.get("policy_summary") or {},
        allowed_actions=["NOOP", "TICK"],
        apply_shield=apply_shield,
        method_id="test_thread_safe",
        mode="multi_agentic",
        coord_method=coord_method,
    )
    driver.reset(42, initial_state)
    agent_ids = driver.agent_ids
    errors: list[str] = []
    barrier = threading.Barrier(len(agent_ids))

    def submit_agent(aid: str) -> None:
        try:
            barrier.wait()
            r = driver.submit_my_action(aid, "NOOP", {}, None)
            if not r.get("received"):
                errors.append(f"{aid}: {r}")
        except Exception as e:
            errors.append(f"{aid}: {e}")

    threads = [threading.Thread(target=submit_agent, args=(aid,)) for aid in agent_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    out = driver.try_advance_step(force=False)
    assert out.get("stepped") is True, out
    env.close()


def test_run_episode_agent_driven_deterministic_backend(_task_and_env_factory) -> None:
    """run_episode_agent_driven with DeterministicAgentDrivenBackend runs to completion and returns valid metrics."""
    task, env_factory = _task_and_env_factory
    backend = DeterministicAgentDrivenBackend(max_steps_to_run=task.max_steps)
    metrics, step_results_per_step = run_episode_agent_driven(
        task=task,
        episode_seed=42,
        env_factory=env_factory,
        agent_driven_backend=backend,
        repo_root=_repo_root(),
    )
    assert isinstance(metrics, dict)
    assert "steps" in metrics
    assert metrics["steps"] == task.max_steps
    assert len(step_results_per_step) == task.max_steps
    assert isinstance(step_results_per_step[0], list)


def test_agent_driven_episode_early_end(_task_and_env_factory) -> None:
    """Backend that stops before max_steps yields step count equal to steps actually run."""
    task, env_factory = _task_and_env_factory
    task.max_steps = 5  # ensure task allows >= 2 steps (shared task may have been set to 1 by other tests)
    backend = DeterministicAgentDrivenBackend(max_steps_to_run=2)
    metrics, step_results_per_step = run_episode_agent_driven(
        task=task,
        episode_seed=99,
        env_factory=env_factory,
        agent_driven_backend=backend,
        repo_root=_repo_root(),
    )
    assert metrics["steps"] == 2
    assert len(step_results_per_step) == 2


def test_agent_driven_metrics_shape(_task_and_env_factory) -> None:
    """Metrics from run_episode_agent_driven have expected keys (throughput, steps, etc.)."""
    task, env_factory = _task_and_env_factory
    task.max_steps = 5  # ensure task allows >= 3 steps (shared task may have been set to 1 by other tests)
    backend = DeterministicAgentDrivenBackend(max_steps_to_run=3)
    metrics, _ = run_episode_agent_driven(
        task=task,
        episode_seed=1,
        env_factory=env_factory,
        agent_driven_backend=backend,
        repo_root=_repo_root(),
    )
    assert "steps" in metrics
    assert "throughput" in metrics
    assert metrics["steps"] == 3


def test_agent_driven_results_schema_valid(tmp_path: Path, _task_and_env_factory) -> None:
    """Agent-driven run produces metrics that fit the same schema as run_episode (steps, throughput, etc.)."""
    task, env_factory = _task_and_env_factory
    task.max_steps = 5  # ensure task allows >= 2 steps (shared task may have been set to 1 by other tests)
    backend = DeterministicAgentDrivenBackend(max_steps_to_run=2)
    log_path = tmp_path / "episode.jsonl"
    metrics, step_results_per_step = run_episode_agent_driven(
        task=task,
        episode_seed=7,
        env_factory=env_factory,
        agent_driven_backend=backend,
        repo_root=_repo_root(),
        log_path=log_path,
    )
    assert metrics.get("steps") == 2
    coord_path = tmp_path / "coord_decisions.jsonl"
    if coord_path.exists():
        lines = coord_path.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            if line:
                rec = json.loads(line)
                assert "method_id" in rec
                assert "t_step" in rec
                assert "actions" in rec


def test_run_benchmark_agent_driven_smoke() -> None:
    """run_benchmark with agent_driven=True and coord_scale completes and writes results (full path smoke)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.benchmarks.runner import run_benchmark

    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        results = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out,
            repo_root=root,
            coord_method="centralized_planner",
            agent_driven=True,
        )
        assert results is not None
        assert results.get("task") == "coord_scale"
        assert results.get("num_episodes") == 1
        episodes = results.get("episodes", [])
        assert len(episodes) == 1
        ep = episodes[0]
        assert "metrics" in ep
        assert ep["metrics"].get("steps", 0) > 0
        assert out.exists()


def test_shield_applied_in_try_advance_step(_task_and_env_factory) -> None:
    """Multi-agentic: submit forbidden action (START_RUN); shield in try_advance_step replaces with NOOP."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver

    task, env_factory = _task_and_env_factory
    task.max_steps = 1
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env = env_factory(initial_state=initial_state, reward_config=task.reward_config, log_path=None)
    env.reset(seed=42, options={"initial_state": initial_state})
    coord_method = CentralizedPlanner()
    coord_method.reset(42, initial_state.get("effective_policy") or {}, {})
    shield_calls: list[dict] = []

    def record_shield(candidate, agent_id, rbac_policy, policy_summary, capability_profile=None):
        shield_calls.append({"candidate": dict(candidate), "agent_id": agent_id})
        from labtrust_gym.baselines.llm.shield import apply_shield

        return apply_shield(candidate, agent_id, rbac_policy or {}, policy_summary or {}, capability_profile)

    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=None,
        blackboard_harness=None,
        rbac_policy={},
        policy_summary=initial_state.get("policy_summary") or {},
        allowed_actions=["NOOP", "TICK"],
        apply_shield=record_shield,
        method_id="test_shield",
        mode="multi_agentic",
        coord_method=coord_method,
    )
    driver.reset(42, initial_state)
    agent_ids = driver.agent_ids
    for i, aid in enumerate(agent_ids):
        action = "START_RUN" if i == 0 else "NOOP"
        driver.submit_my_action(aid, action, {}, None)
    out = driver.try_advance_step(force=False)
    assert out.get("stepped") is True, out
    assert len(shield_calls) >= 1
    env.close()


def test_risk_injector_mutate_in_multi_agentic(_task_and_env_factory) -> None:
    """Multi-agentic driver with risk injector: mutate_obs and mutate_actions are called."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )
    from labtrust_gym.baselines.llm.shield import apply_shield
    from labtrust_gym.benchmarks.agent_driven_driver import AgentDrivenDriver

    task, env_factory = _task_and_env_factory
    task.max_steps = 1
    initial_state = task.get_initial_state(42, policy_root=_repo_root())
    env = env_factory(initial_state=initial_state, reward_config=task.reward_config, log_path=None)
    env.reset(seed=42, options={"initial_state": initial_state})
    coord_method = CentralizedPlanner()
    coord_method.reset(42, initial_state.get("effective_policy") or {}, {})
    mutate_obs_count = 0
    mutate_actions_count = 0

    class MockInjector:
        def reset(self, seed, _):
            pass

        def mutate_obs(self, obs):
            nonlocal mutate_obs_count
            mutate_obs_count += 1
            return obs, []

        def mutate_actions(self, actions_dict):
            nonlocal mutate_actions_count
            mutate_actions_count += 1
            return actions_dict, []

    driver = AgentDrivenDriver(
        env=env,
        task=task,
        risk_injector=MockInjector(),
        blackboard_harness=None,
        rbac_policy={},
        policy_summary=initial_state.get("policy_summary") or {},
        allowed_actions=["NOOP", "TICK"],
        apply_shield=apply_shield,
        method_id="test_risk",
        mode="multi_agentic",
        coord_method=coord_method,
    )
    driver.reset(42, initial_state)
    for aid in driver.agent_ids:
        driver.submit_my_action(aid, "NOOP", {}, None)
    out = driver.try_advance_step(force=False)
    assert out.get("stepped") is True, out
    assert mutate_obs_count >= 1
    assert mutate_actions_count >= 1
    env.close()


def test_agent_driven_scenario_ref_attack_single() -> None:
    """_run_agent_driven_scenario_ref_attack with mode=single returns same result as simulation-centric."""
    from labtrust_gym.benchmarks.security_runner import (
        _run_agent_driven_scenario_ref_attack,
        load_prompt_injection_scenarios,
    )

    root = _repo_root()
    scenarios = load_prompt_injection_scenarios(root)
    if not scenarios:
        pytest.skip("no prompt_injection_scenarios")
    scenario_id = scenarios[0].get("scenario_id")
    if not scenario_id:
        pytest.skip("scenario_id missing")
    passed, err = _run_agent_driven_scenario_ref_attack(scenario_id, scenarios, root, 42, mode="single")
    assert isinstance(passed, bool)
    assert err is None or isinstance(err, str)


@pytest.mark.timeout(180)
def test_coord_pack_multi_agentic_smoke() -> None:
    """run_coordination_security_pack with multi_agentic=True completes and produces summary."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.studies.coordination_security_pack import (
        run_coordination_security_pack,
    )

    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "pack_out"
        run_coordination_security_pack(
            out_dir=out_dir,
            repo_root=root,
            seed_base=42,
            methods_from="fixed",
            injections_from="fixed",
            scales_from="default",
            scale_ids_filter=["small_smoke"],
            workers=1,
            multi_agentic=True,
        )
        summary_path = out_dir / "pack_summary.csv"
        assert summary_path.exists()
        gate_path = out_dir / "pack_gate.md"
        assert gate_path.exists()
        gate_summary_path = out_dir / "SECURITY" / "coord_pack_gate_summary.json"
        assert gate_summary_path.is_file(), "multi_agentic coord pack must write SECURITY/coord_pack_gate_summary.json"
        import json

        gate_summary = json.loads(gate_summary_path.read_text(encoding="utf-8"))
        assert "overall_pass" in gate_summary
        assert "total_cells" in gate_summary
        assert "passed" in gate_summary
        assert "failed" in gate_summary
