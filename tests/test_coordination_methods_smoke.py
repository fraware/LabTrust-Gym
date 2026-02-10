"""
Smoke tests for coordination methods: instantiate each (except marl_ppo if deps missing),
run 50 steps on tiny scale, ensure valid action dict for all active agents.

Parametrized over all method_ids from policy/coordination/coordination_methods.v0.1.yaml;
skips methods that require optional deps (marl_ppo, llm_constrained without llm_agent).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from labtrust_gym.baselines.coordination.interface import (
    ACTION_NOOP,
    CoordinationMethod,
    action_dict_to_index_and_info,
)
from labtrust_gym.baselines.coordination.registry import make_coordination_method
from labtrust_gym.policy.coordination import load_coordination_methods


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _method_ids_from_policy() -> list[str]:
    """All method_ids from coordination_methods.v0.1.yaml (for parametrization)."""
    repo = _repo_root()
    path = repo / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
    if not path.exists():
        return []
    registry = load_coordination_methods(path)
    return sorted(registry.keys())


def _tiny_scale_policy() -> dict:
    """Minimal policy with zone_layout for coordination methods."""
    return {
        "zone_layout": {
            "zones": [
                {
                    "zone_id": "Z_A",
                    "name": "A",
                    "kind": "STAGING",
                    "temp_band": "AMBIENT_20_25",
                },
                {
                    "zone_id": "Z_B",
                    "name": "B",
                    "kind": "STAGING",
                    "temp_band": "AMBIENT_20_25",
                },
            ],
            "graph_edges": [{"from": "Z_A", "to": "Z_B", "travel_s": 10}],
            "device_placement": [
                {"device_id": "DEV_1", "zone_id": "Z_B"},
            ],
        },
    }


def _fake_obs(agent_ids: list[str], t: int) -> dict:
    """Minimal obs dict per agent for one step."""
    out = {}
    for i, aid in enumerate(agent_ids):
        out[aid] = {
            "my_zone_idx": 1 + (i % 2),
            "zone_id": "Z_B" if i % 2 else "Z_A",
            "queue_by_device": [{"device_id": "DEV_1", "queue_len": 0, "queue_head": None}],
            "queue_has_head": [0],
            "log_frozen": 0,
            "door_restricted_open": 0,
            "restricted_zone_frozen": 0,
        }
    return out


def _run_50_steps(method: CoordinationMethod, policy: dict, scale_config: dict) -> None:
    """Run 50 steps with fake obs; assert valid action dict per agent."""
    method.reset(seed=42, policy=policy, scale_config=scale_config)
    agent_ids = ["worker_0", "worker_1"]
    infos: dict = {}
    for t in range(50):
        obs = _fake_obs(agent_ids, t)
        actions_dict = method.propose_actions(obs, infos, t)
        assert isinstance(actions_dict, dict)
        for aid in agent_ids:
            assert aid in actions_dict
            ad = actions_dict[aid]
            assert "action_index" in ad
            idx = ad["action_index"]
            assert isinstance(idx, int)
            assert 0 <= idx <= 5
            action_index, action_info = action_dict_to_index_and_info(ad)
            assert 0 <= action_index <= 5


def _make_llm_agent_for_smoke(repo_root: Path) -> Any:
    """Build a deterministic LLM agent for llm_constrained (no API key; same as contract test)."""
    from labtrust_gym.baselines.llm.agent import (
        DeterministicConstrainedBackend,
        LLMAgentWithShield,
    )
    from labtrust_gym.engine.rbac import load_rbac_policy

    rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
    rbac_policy = load_rbac_policy(rbac_path) if rbac_path.exists() else {}
    capability_policy = {}
    try:
        from labtrust_gym.security.agent_capabilities import load_agent_capabilities
        capability_policy = load_agent_capabilities(repo_root)
    except Exception:
        pass
    pz_to_engine = {"worker_0": "A_WORKER_0001", "worker_1": "A_WORKER_0002"}
    return LLMAgentWithShield(
        backend=DeterministicConstrainedBackend(seed=42, default_action_type="NOOP"),
        rbac_policy=rbac_policy,
        pz_to_engine=pz_to_engine,
        strict_signatures=False,
        key_registry={},
        get_private_key=lambda _: None,
        capability_policy=capability_policy,
    )


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_coordination_method_smoke_50_steps(method_id: str) -> None:
    """Every registered method runs 50 steps with minimal obs; skip if optional deps missing."""
    if method_id == "marl_ppo":
        pytest.skip("marl_ppo requires a trained model (not provided in smoke)")
    policy = _tiny_scale_policy()
    scale_config = {"num_agents_total": 2, "num_sites": 1}
    repo_root = _repo_root()
    kwargs: dict = {"repo_root": repo_root, "scale_config": scale_config}
    if method_id == "llm_constrained":
        try:
            kwargs["llm_agent"] = _make_llm_agent_for_smoke(repo_root)
            kwargs["pz_to_engine"] = {"worker_0": "A_WORKER_0001", "worker_1": "A_WORKER_0002"}
        except ImportError as e:
            pytest.skip(f"llm_constrained deps: {e}")
    try:
        method = make_coordination_method(method_id, policy, **kwargs)
    except (ValueError, ImportError, NotImplementedError) as e:
        if "marl_ppo" in method_id or "trained model" in str(e).lower():
            pytest.skip(f"{method_id}: optional deps missing — {e}")
        raise
    if not isinstance(method, CoordinationMethod):
        pytest.skip(f"{method_id}: factory returned non-method")
    try:
        _run_50_steps(method, policy, scale_config)
    except NotImplementedError as e:
        if "trained model" in str(e).lower() or "marl_ppo" in method_id:
            pytest.skip(f"{method_id}: {e}")
        raise


def test_centralized_planner_compute_budget() -> None:
    """Centralized planner with compute_budget limits assignments."""
    from labtrust_gym.baselines.coordination.methods.centralized_planner import (
        CentralizedPlanner,
    )

    policy = _tiny_scale_policy()
    scale_config = {"num_agents_total": 3, "num_sites": 1}
    method = CentralizedPlanner(compute_budget=1)
    method.reset(42, policy, scale_config)
    agents = ["worker_0", "worker_1", "worker_2"]
    obs = _fake_obs(agents, 0)
    actions_dict = method.propose_actions(obs, {}, 0)
    assert len(actions_dict) == 3
    non_noop = sum(1 for a in actions_dict.values() if a.get("action_index") != ACTION_NOOP)
    assert non_noop <= 1


def test_marl_ppo_stub_skip_if_no_deps() -> None:
    """marl_ppo is skipped (or raises) when SB3 not installed."""
    try:
        import gymnasium  # noqa: F401
        import stable_baselines3  # noqa: F401

        pytest.skip("SB3 installed; test only runs when marl extra missing")
    except ImportError:
        pass
    with pytest.raises((ImportError, NotImplementedError)):
        make_coordination_method(
            "marl_ppo",
            {},
            repo_root=None,
            scale_config={"num_agents_total": 2},
        )


def test_llm_constrained_requires_llm_agent() -> None:
    """llm_constrained raises if llm_agent not provided."""
    with pytest.raises(ValueError, match="llm_constrained requires llm_agent"):
        make_coordination_method(
            "llm_constrained",
            _tiny_scale_policy(),
            repo_root=None,
            scale_config={},
        )


def test_unknown_method_raises() -> None:
    """Unknown method_id raises ValueError."""
    with pytest.raises(ValueError, match="Unknown coordination method_id"):
        make_coordination_method("nonexistent", {}, repo_root=None)
