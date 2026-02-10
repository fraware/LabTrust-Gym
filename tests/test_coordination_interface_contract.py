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
from labtrust_gym.policy.coordination import load_coordination_methods


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
        f"worker_{i}": scale_agents[i]["agent_id"]
        for i in range(len(scale_agents))
        if i < len(scale_agents)
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
    except (ValueError, NotImplementedError) as e:
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
    scale_probe_state = generate_scaled_initial_state(
        scale_config, repo_root, 42
    )
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

    coord_method = _make_coord_method_for_contract(
        method_id, repo_root, scale_probe_state, scale_config_dict
    )
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
        except NotImplementedError as e:
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
            assert idx in VALID_ACTION_INDICES, (
                f"{method_id} step {t} {agent_id}: action_index must be 0..5, got {idx}"
            )
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
        actions2 = {aid: action_dict_to_index_and_info(actions_dict2.get(aid, {"action_index": 0}))[0] for aid in env2.agents}
        action_infos2 = {aid: action_dict_to_index_and_info(actions_dict2.get(aid, {"action_index": 0}))[1] for aid in env2.agents if action_dict_to_index_and_info(actions_dict2.get(aid, {"action_index": 0}))[1]}
        obs2, _, _, _, infos2 = env2.step(actions2, action_infos=action_infos2)
    env2.close()


def test_coordination_contract_run_episode_smoke() -> None:
    """run_episode with centralized_planner completes (integration with runner)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.benchmarks.runner import run_benchmark
    import tempfile

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


def test_coordination_contract_runner_detector_advisor_smoke() -> None:
    """run_benchmark with llm_detector_throttle_advisor completes (runner path, default detector)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.benchmarks.runner import run_benchmark
    import tempfile

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
