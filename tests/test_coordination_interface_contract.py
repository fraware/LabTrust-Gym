"""
Coordination Baseline Contract v0.1: every method_id in the policy registry
must implement the CoordinationMethod interface and pass a short TaskG run.

- Loads every method_id from policy/coordination/coordination_methods.v0.1.yaml.
- Instantiates via registry (deterministic backends; llm_constrained gets mock).
- Runs 5 steps in TaskG with seed=42.
- Asserts: actions for all agents, schema-valid action_index (0..5), determinism.

No network: all methods run with deterministic backends (repo_root set; llm_* use
Deterministic*Backend). marl_ppo skipped when optional deps missing.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.interface import (
    VALID_ACTION_INDICES,
    CoordinationMethod,
    action_dict_to_index_and_info,
)
from labtrust_gym.baselines.coordination.registry import make_coordination_method
from labtrust_gym.benchmarks.coordination_scale import (
    CoordinationScaleConfig,
    generate_scaled_initial_state,
)
from labtrust_gym.benchmarks.tasks import get_task
from labtrust_gym.policy.coordination import (
    adapt_submission,
    load_coordination_methods,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _contract_scale_config() -> CoordinationScaleConfig:
    """Minimal scale for contract test: 3 agents, 5 steps."""
    return CoordinationScaleConfig(
        num_agents_total=3,
        role_mix={
            "ROLE_RUNNER": 0.5,
            "ROLE_ANALYTICS": 0.4,
            "ROLE_RECEPTION": 0.1,
        },
        num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=1.0,
        horizon_steps=5,
        timing_mode="explicit",
        partner_id=None,
    )


def _method_ids_from_policy() -> list[str]:
    """All method_ids from coordination_methods.v0.1.yaml."""
    repo = _repo_root()
    path = repo / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
    if not path.exists():
        pytest.skip("coordination_methods.v0.1.yaml not found")
    registry = load_coordination_methods(path)
    return sorted(registry.keys())


def _make_coord_method_for_contract(
    method_id: str,
    repo_root: Path,
    scale_probe_state: dict,
    scale_config_dict: dict,
) -> CoordinationMethod | None:
    """Instantiate coordination method for contract test; None if skipped (e.g. marl_ppo)."""
    policy_for_coord = (scale_probe_state.get("effective_policy") or {}).copy()
    scale_agents = scale_probe_state.get("agents") or []
    pz_to_engine = {
        f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
    }
    if pz_to_engine:
        policy_for_coord.setdefault("pz_to_engine", pz_to_engine)
    scale_config_dict = dict(scale_config_dict)
    scale_config_dict.setdefault("seed", 42)

    if method_id == "llm_constrained":
        try:
            from labtrust_gym.baselines.llm.agent import (
                DeterministicConstrainedBackend,
                LLMAgentWithShield,
            )
            from labtrust_gym.engine.rbac import load_rbac_policy
            from labtrust_gym.security.agent_capabilities import load_agent_capabilities
        except ImportError as e:
            pytest.skip(f"llm_constrained deps: {e}")
        rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
        rbac_policy = load_rbac_policy(rbac_path) if rbac_path.exists() else {}
        capability_policy = {}
        try:
            from labtrust_gym.security.agent_capabilities import load_agent_capabilities

            capability_policy = load_agent_capabilities(repo_root)
        except Exception:
            pass
        llm_agent = LLMAgentWithShield(
            backend=DeterministicConstrainedBackend(seed=42, default_action_type="NOOP"),
            rbac_policy=rbac_policy,
            pz_to_engine=pz_to_engine,
            strict_signatures=False,
            key_registry={},
            get_private_key=lambda _: None,
            capability_policy=capability_policy,
        )
        return make_coordination_method(
            method_id,
            policy_for_coord,
            repo_root=repo_root,
            scale_config=scale_config_dict,
            llm_agent=llm_agent,
            pz_to_engine=pz_to_engine,
        )
    try:
        return make_coordination_method(
            method_id,
            policy_for_coord,
            repo_root=repo_root,
            scale_config=scale_config_dict,
        )
    except ImportError as e:
        if "marl_ppo" in method_id or "stable_baselines3" in str(e).lower():
            return None
        raise
    except (ValueError, NotImplementedError, RuntimeError) as e:
        if "marl_ppo" in method_id or "SB3" in str(e):
            return None
        raise


@pytest.fixture(scope="module")
def _contract_env_factory_and_state():
    """Build env_factory and initial_state for TaskG contract run (module scope)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    repo_root = _repo_root()
    scale_config = _contract_scale_config()
    scale_probe_state = generate_scaled_initial_state(scale_config, repo_root, 42)
    scale_config_dict = asdict(scale_config)
    scale_config_dict["seed"] = 42
    scale_agents = scale_probe_state.get("agents") or []
    scale_device_ids = scale_probe_state.get("_scale_device_ids") or []
    scale_zone_ids = scale_probe_state.get("_scale_zone_ids") or []

    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    policy_dir = repo_root / "policy"

    def _make_env(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=0,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config,
            policy_dir=policy_dir,
            log_path=log_path,
            scale_agents=scale_agents,
            scale_device_ids=scale_device_ids,
            scale_zone_ids=scale_zone_ids,
        )

    task = get_task("coord_scale")
    original_max_steps = task.max_steps
    task.max_steps = 5
    try:
        yield _make_env, scale_probe_state, scale_config_dict, task
    finally:
        task.max_steps = original_max_steps


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_coordination_method_contract(
    method_id: str,
    _contract_env_factory_and_state,
) -> None:
    """Every registered method: instantiate, run 5 steps TaskG, assert actions + schema + determinism."""
    env_factory, scale_probe_state, scale_config_dict, task = _contract_env_factory_and_state
    repo_root = _repo_root()

    coord_method = _make_coord_method_for_contract(method_id, repo_root, scale_probe_state, scale_config_dict)
    if coord_method is None:
        pytest.skip(f"{method_id}: optional deps missing (e.g. marl_ppo)")
    assert isinstance(coord_method, CoordinationMethod)

    initial_state = task.get_initial_state(42)
    initial_state["effective_policy"] = scale_probe_state.get("effective_policy")
    reward_config = task.reward_config or {}

    env = env_factory(initial_state, reward_config)
    obs, _ = env.reset(seed=42, options={"initial_state": initial_state})
    coord_method.reset(42, initial_state.get("effective_policy") or {}, scale_config_dict)
    infos: dict = {}
    actions_per_step: list[dict] = []

    for t in range(5):
        try:
            actions_dict = coord_method.propose_actions(obs, infos, t)
        except (NotImplementedError, RuntimeError) as e:
            if "marl_ppo" in method_id or "trained model" in str(e).lower():
                pytest.skip(f"{method_id}: {e}")
            raise
        assert isinstance(actions_dict, dict), f"{method_id} step {t}: propose_actions must return dict"
        required_agents = set(env.agents)
        assert set(actions_dict.keys()) >= required_agents, (
            f"{method_id} step {t}: missing actions for {required_agents - set(actions_dict.keys())}"
        )
        actions = {}
        action_infos = {}
        for agent_id in env.agents:
            ad = actions_dict.get(agent_id, {"action_index": 0})
            assert "action_index" in ad, f"{method_id} step {t} {agent_id}: missing action_index"
            idx = ad["action_index"]
            assert idx in VALID_ACTION_INDICES, f"{method_id} step {t} {agent_id}: action_index must be 0..5, got {idx}"
            action_index, info = action_dict_to_index_and_info(ad)
            actions[agent_id] = action_index
            if info:
                action_infos[agent_id] = info
        actions_per_step.append(dict(actions_dict))
        obs, _rewards, _term, _trunc, infos = env.step(actions, action_infos=action_infos)
    env.close()

    # Determinism: run again with same seed and compare actions
    env2 = env_factory(initial_state, reward_config)
    obs2, _ = env2.reset(seed=42, options={"initial_state": initial_state})
    coord_method.reset(42, initial_state.get("effective_policy") or {}, scale_config_dict)
    infos2: dict = {}
    for t in range(5):
        actions_dict2 = coord_method.propose_actions(obs2, infos2, t)
        assert set(actions_dict2.keys()) >= set(env2.agents)
        for aid in env2.agents:
            a1 = actions_per_step[t].get(aid, {"action_index": 0})
            a2 = actions_dict2.get(aid, {"action_index": 0})
            assert a1.get("action_index") == a2.get("action_index"), (
                f"{method_id} determinism step {t} {aid}: {a1.get('action_index')} != {a2.get('action_index')}"
            )
        actions2 = {
            aid: action_dict_to_index_and_info(actions_dict2.get(aid, {"action_index": 0}))[0] for aid in env2.agents
        }
        action_infos2 = {
            aid: action_dict_to_index_and_info(actions_dict2.get(aid, {"action_index": 0}))[1]
            for aid in env2.agents
            if action_dict_to_index_and_info(actions_dict2.get(aid, {"action_index": 0}))[1]
        }
        obs2, _, _, _, infos2 = env2.step(actions2, action_infos=action_infos2)
    env2.close()


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_coordination_combine_submissions_contract(
    method_id: str,
    _contract_env_factory_and_state,
) -> None:
    """Every registered method: combine_submissions with mock submissions returns valid joint action."""
    env_factory, scale_probe_state, scale_config_dict, task = _contract_env_factory_and_state
    repo_root = _repo_root()

    coord_method = _make_coord_method_for_contract(method_id, repo_root, scale_probe_state, scale_config_dict)
    if coord_method is None:
        pytest.skip(f"{method_id}: optional deps missing (e.g. marl_ppo)")
    assert hasattr(coord_method, "combine_submissions")

    initial_state = task.get_initial_state(42)
    initial_state["effective_policy"] = scale_probe_state.get("effective_policy")
    reward_config = task.reward_config or {}
    env = env_factory(initial_state, reward_config)
    obs, _ = env.reset(seed=42, options={"initial_state": initial_state})
    coord_method.reset(42, initial_state.get("effective_policy") or {}, scale_config_dict)
    infos: dict = {}

    # Mock submissions: one action per agent (NOOP); combine_submissions must return valid joint action
    submissions = {aid: {"action_index": 0, "action_type": "NOOP"} for aid in obs}
    result = coord_method.combine_submissions(submissions, obs, infos, 0)

    assert isinstance(result, dict), f"{method_id}: combine_submissions must return dict"
    required_agents = set(env.agents)
    assert set(result.keys()) >= required_agents, (
        f"{method_id}: combine_submissions must return keys for all agents {required_agents}"
    )
    for agent_id in required_agents:
        ad = result.get(agent_id, {"action_index": 0})
        assert "action_index" in ad, f"{method_id} {agent_id}: missing action_index"
        idx = ad["action_index"]
        assert idx in VALID_ACTION_INDICES, f"{method_id} {agent_id}: action_index must be in 0..5, got {idx}"
    env.close()


def test_combine_submissions_default_shape_and_noop_fill() -> None:
    """Default combine_submissions: joint action has action_index per agent; missing agents get NOOP."""
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )

    method = CentralizedPlanner()
    method.reset(0, {}, {})
    obs = {"worker_0": {"zone_id": "Z1"}, "worker_1": {"zone_id": "Z1"}}
    infos = {}
    submissions = {
        "worker_0": {"action_index": 1, "action_type": "TICK"},
        "worker_1": {"action_type": "NOOP"},  # no action_index; default fills from action_type
    }
    result = method.combine_submissions(submissions, obs, infos, 0)
    assert set(result.keys()) == {"worker_0", "worker_1"}
    assert result["worker_0"]["action_index"] == 1
    assert result["worker_1"]["action_index"] == 0
    # Missing agent in submissions but in obs gets NOOP
    obs3 = {"worker_0": {}, "worker_1": {}, "worker_2": {}}
    sub2 = {"worker_0": {"action_index": 3}}
    result2 = method.combine_submissions(sub2, obs3, infos, 0)
    assert result2["worker_0"]["action_index"] == 3
    assert result2["worker_1"]["action_index"] == 0
    assert result2["worker_2"]["action_index"] == 0


def test_coordination_contract_run_episode_smoke() -> None:
    """run_episode with centralized_planner completes (integration with runner)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = _repo_root()
    scale_config = _contract_scale_config()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out,
            repo_root=repo_root,
            coord_method="centralized_planner",
            scale_config_override=scale_config,
        )
        assert out.exists()


def test_coordination_scale_combine_path_integration() -> None:
    """When N > coord_propose_actions_max_agents, runner uses combine_submissions path."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")

    from labtrust_gym.benchmarks.coordination_scale import (
        CoordinationScaleConfig,
        generate_scaled_initial_state,
    )
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    repo_root = _repo_root()
    scale_config = CoordinationScaleConfig(
        num_agents_total=3,
        role_mix={"ROLE_RUNNER": 0.5, "ROLE_ANALYTICS": 0.4, "ROLE_RECEPTION": 0.1},
        num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=1.0,
        horizon_steps=3,
        timing_mode="explicit",
        partner_id=None,
        coord_propose_actions_max_agents=2,
    )
    scale_probe = generate_scaled_initial_state(scale_config, repo_root, 42)
    task = get_task("coord_scale")
    task.max_steps = 3
    task.scale_config = scale_config
    scale_config_dict = {
        "num_agents_total": 3,
        "role_mix": scale_config.role_mix,
        "num_devices_per_type": scale_config.num_devices_per_type,
        "num_sites": 1,
        "specimens_per_min": 3.0,
        "horizon_steps": 3,
        "timing_mode": "explicit",
        "partner_id": None,
        "coord_propose_actions_max_agents": 2,
    }
    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    coord_method = make_coordination_method(
        "centralized_planner",
        scale_probe.get("effective_policy") or {},
        repo_root=repo_root,
        scale_config=scale_config_dict,
    )
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

    initial_state = task.get_initial_state(42)
    initial_state["effective_policy"] = scale_probe.get("effective_policy")
    reward_config = task.reward_config or {}
    env = env_factory(initial_state, reward_config)
    obs, _ = env.reset(seed=42, options={"initial_state": initial_state})
    coord_method.reset(42, initial_state.get("effective_policy") or {}, scale_config_dict)
    infos = {}
    for step_t in range(3):
        submissions = {}
        for agent_id in env.agents:
            if agent_id in scripted_agents_map:
                ret = scripted_agents_map[agent_id].act(obs.get(agent_id, {}), agent_id)
                submissions[agent_id] = {
                    "action_index": ret[0],
                    **(ret[1] if len(ret) > 1 else {}),
                }
            else:
                submissions[agent_id] = {"action_index": 0}
        actions_dict = coord_method.combine_submissions(submissions, obs, infos, step_t)
        assert set(actions_dict.keys()) >= set(env.agents)
        from labtrust_gym.baselines.coordination.interface import (
            VALID_ACTION_INDICES,
            action_dict_to_index_and_info,
        )

        actions = {}
        action_infos = {}
        for agent_id in env.agents:
            ad = actions_dict.get(agent_id, {"action_index": 0})
            idx = ad["action_index"]
            assert idx in VALID_ACTION_INDICES
            act_idx, info = action_dict_to_index_and_info(ad)
            actions[agent_id] = act_idx
            action_infos[agent_id] = info
        obs, _, _, _, infos = env.step(actions, action_infos=action_infos)
    env.close()


def test_adapt_submission_action_bid_vote() -> None:
    """adapt_submission returns correct shape for action, bid, and vote."""
    out_action = adapt_submission("action", 0, {"reason_code": "r", "args": {}})
    assert out_action["action_index"] == 0
    assert out_action.get("reason_code") == "r"

    out_bid = adapt_submission("bid", 0, {"cost": 5, "device_id": "d1", "reason_code": "x"})
    assert "bid" in out_bid
    assert out_bid["bid"].get("cost") == 5
    assert out_bid["bid"].get("device_id") == "d1"
    assert "reason_code" not in out_bid["bid"]

    out_vote = adapt_submission("vote", 1, {"vote": 2})
    assert out_vote.get("vote") == 2
    out_vote_default = adapt_submission("vote", 1, {})
    assert out_vote_default.get("vote") == 1


def test_scale_per_agent_llm_combine() -> None:
    """Combine path with 10 mock LLM agents: combine_submissions called, metrics valid."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")

    from labtrust_gym.baselines.llm.agent import (
        DeterministicConstrainedBackend,
        LLMAgentWithShield,
    )
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    repo_root = _repo_root()
    scale_config = CoordinationScaleConfig(
        num_agents_total=10,
        role_mix={"ROLE_RUNNER": 0.6, "ROLE_ANALYTICS": 0.4},
        num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=1.0,
        horizon_steps=2,
        timing_mode="explicit",
        partner_id=None,
        coord_propose_actions_max_agents=5,
    )
    scale_probe = generate_scaled_initial_state(scale_config, repo_root, 42)
    task = get_task("coord_scale")
    if task is None:
        pytest.skip("coord_scale task not registered")
    task.max_steps = 2
    task.scale_config = scale_config
    scale_config_dict = asdict(scale_config)
    coord_method = make_coordination_method(
        "centralized_planner",
        scale_probe.get("effective_policy") or {},
        repo_root=repo_root,
        scale_config=scale_config_dict,
    )
    agents = scale_probe.get("agents") or []
    device_ids = scale_probe.get("_scale_device_ids") or []
    zone_ids = scale_probe.get("_scale_zone_ids") or []
    policy_dir = repo_root / "policy"
    pz_to_engine = {f"worker_{i}": agents[i]["agent_id"] for i in range(len(agents))}
    backend = DeterministicConstrainedBackend(seed=42, default_action_type="NOOP")
    scripted_agents_map = {
        f"worker_{i}": LLMAgentWithShield(
            backend=backend,
            rbac_policy={},
            pz_to_engine=pz_to_engine,
        )
        for i in range(len(agents))
    }

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

    from labtrust_gym.benchmarks.runner import run_episode

    initial_state = task.get_initial_state(42, policy_root=repo_root)
    initial_state["effective_policy"] = scale_probe.get("effective_policy")
    metrics, step_results = run_episode(
        task=task,
        episode_seed=42,
        env_factory=env_factory,
        scripted_agents_map=scripted_agents_map,
        coord_method=coord_method,
        repo_root=repo_root,
        initial_state_overrides={"effective_policy": scale_probe.get("effective_policy")},
    )
    assert isinstance(metrics, dict)
    assert "steps" in metrics
    assert metrics["steps"] == 2
    assert len(step_results) == 2


@pytest.mark.slow
def test_scale_per_agent_llm_combine_many_agents() -> None:
    """Combine path with 50+ agents: per-agent LLM population, combine path used, metrics valid."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")

    from labtrust_gym.baselines.llm.agent import (
        DeterministicConstrainedBackend,
        LLMAgentWithShield,
    )
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    repo_root = _repo_root()
    num_agents = 50
    n_max = 20
    horizon_steps = 3
    scale_config = CoordinationScaleConfig(
        num_agents_total=num_agents,
        role_mix={"ROLE_RUNNER": 0.6, "ROLE_ANALYTICS": 0.4},
        num_devices_per_type={"CHEM_ANALYZER": 1, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=1.0,
        horizon_steps=horizon_steps,
        timing_mode="explicit",
        partner_id=None,
        coord_propose_actions_max_agents=n_max,
    )
    scale_probe = generate_scaled_initial_state(scale_config, repo_root, 42)
    task = get_task("coord_scale")
    if task is None:
        pytest.skip("coord_scale task not registered")
    task.max_steps = horizon_steps
    task.scale_config = scale_config
    scale_config_dict = asdict(scale_config)
    coord_method = make_coordination_method(
        "centralized_planner",
        scale_probe.get("effective_policy") or {},
        repo_root=repo_root,
        scale_config=scale_config_dict,
    )
    agents = scale_probe.get("agents") or []
    assert len(agents) >= num_agents, "scale probe must yield at least num_agents"
    device_ids = scale_probe.get("_scale_device_ids") or []
    zone_ids = scale_probe.get("_scale_zone_ids") or []
    policy_dir = repo_root / "policy"
    pz_to_engine = {f"worker_{i}": agents[i]["agent_id"] for i in range(len(agents))}
    backend = DeterministicConstrainedBackend(seed=42, default_action_type="NOOP")
    scripted_agents_map = {
        f"worker_{i}": LLMAgentWithShield(
            backend=backend,
            rbac_policy={},
            pz_to_engine=pz_to_engine,
        )
        for i in range(len(agents))
    }
    assert len(scripted_agents_map) >= num_agents

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

    from labtrust_gym.benchmarks.runner import run_episode

    initial_state = task.get_initial_state(42, policy_root=repo_root)
    initial_state["effective_policy"] = scale_probe.get("effective_policy")
    metrics, step_results = run_episode(
        task=task,
        episode_seed=42,
        env_factory=env_factory,
        scripted_agents_map=scripted_agents_map,
        coord_method=coord_method,
        repo_root=repo_root,
        initial_state_overrides={"effective_policy": scale_probe.get("effective_policy")},
    )
    assert isinstance(metrics, dict)
    assert "steps" in metrics
    assert metrics["steps"] == horizon_steps
    assert len(step_results) == horizon_steps
    assert len(scripted_agents_map) >= 50


def test_coordination_contract_runner_detector_advisor_smoke() -> None:
    """run_benchmark with llm_detector_throttle_advisor completes (runner path, default detector)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = _repo_root()
    scale_config = _contract_scale_config()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results_detector.json"
        results = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out,
            repo_root=repo_root,
            coord_method="llm_detector_throttle_advisor",
            scale_config_override=scale_config,
        )
        assert out.exists()
        assert results is not None
        assert isinstance(results, dict)
