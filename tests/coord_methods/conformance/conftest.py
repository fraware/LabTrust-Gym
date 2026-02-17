"""
Shared fixtures for CoordinationMethod conformance suite.
Minimal policy/obs and scale_config; method instantiation via registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from labtrust_gym.baselines.coordination.interface import CoordinationMethod
from labtrust_gym.baselines.coordination.registry import make_coordination_method
from labtrust_gym.policy.coordination import load_coordination_methods


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _conformance_config() -> dict[str, Any]:
    """Load conformance_config.yaml."""
    path = Path(__file__).resolve().parent / "conformance_config.yaml"
    if not path.exists():
        return {}
    try:
        import yaml
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _method_ids_from_policy() -> list[str]:
    """All method_ids from coordination_methods.v0.1.yaml."""
    repo = _repo_root()
    path = repo / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
    if not path.exists():
        pytest.skip("coordination_methods.v0.1.yaml not found")
    registry = load_coordination_methods(path)
    return sorted(registry.keys())


def _minimal_policy() -> dict[str, Any]:
    """Minimal policy with zone_layout for conformance (no env required)."""
    repo = _repo_root()
    zone_path = repo / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
    if zone_path.exists():
        from labtrust_gym.policy.loader import load_yaml
        data = load_yaml(zone_path)
        layout = data.get("zone_layout") or data
    else:
        layout = {"zones": [], "graph_edges": [], "device_placement": []}
    return {
        "zone_layout": layout,
        "pz_to_engine": {"worker_0": "ops_0", "worker_1": "runner_0", "worker_2": "runner_1"},
    }


def _minimal_obs(agent_ids: list[str], t: int) -> dict[str, Any]:
    """Minimal obs for conformance (deterministic, same as kernel determinism test)."""
    obs: dict[str, Any] = {}
    for i, aid in enumerate(agent_ids):
        obs[aid] = {
            "my_zone_idx": 1 + (i + t) % 2,
            "zone_id": "Z_SORTING_LANES" if i == 0 else "Z_ANALYZER_HALL_A",
            "queue_has_head": [0] * 2,
            "queue_by_device": [
                {"queue_head": "", "queue_len": 0},
                {"queue_head": "", "queue_len": 0},
            ],
            "log_frozen": 0,
        }
    return obs


def _minimal_scale_config(seed: int = 42) -> dict[str, Any]:
    return {
        "num_agents_total": 3,
        "horizon_steps": 10,
        "seed": seed,
    }


def _scale_probe_state() -> dict[str, Any]:
    """Minimal scale_probe_state for make_coordination_method (effective_policy + agents)."""
    policy = _minimal_policy()
    agents = [
        {"agent_id": "ops_0"},
        {"agent_id": "runner_0"},
        {"agent_id": "runner_1"},
    ]
    return {
        "effective_policy": policy,
        "agents": agents,
    }


def make_coord_method_for_conformance(
    method_id: str,
    repo_root: Path,
    scale_config: dict[str, Any],
) -> CoordinationMethod | None:
    """Instantiate coordination method for conformance; None if skipped (e.g. marl_ppo)."""
    scale_probe = _scale_probe_state()
    policy_for_coord = (scale_probe.get("effective_policy") or {}).copy()
    scale_probe.setdefault("pz_to_engine", policy_for_coord.get("pz_to_engine") or {})
    if method_id == "llm_constrained":
        try:
            from labtrust_gym.baselines.llm.agent import (
                DeterministicConstrainedBackend,
                LLMAgentWithShield,
            )
            from labtrust_gym.engine.rbac import load_rbac_policy
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
            backend=DeterministicConstrainedBackend(seed=scale_config.get("seed", 42), default_action_type="NOOP"),
            rbac_policy=rbac_policy,
            pz_to_engine=scale_probe["pz_to_engine"],
            strict_signatures=False,
            key_registry={},
            get_private_key=lambda _: None,
            capability_policy=capability_policy,
        )
        return make_coordination_method(
            method_id,
            policy_for_coord,
            repo_root=repo_root,
            scale_config=scale_config,
            llm_agent=llm_agent,
            pz_to_engine=scale_probe["pz_to_engine"],
        )
    try:
        return make_coordination_method(
            method_id,
            policy_for_coord,
            repo_root=repo_root,
            scale_config=scale_config,
        )
    except (ImportError, ValueError, NotImplementedError, RuntimeError) as e:
        if "marl_ppo" in method_id or "stable_baselines3" in str(e).lower() or "SB3" in str(e):
            return None
        raise


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return _repo_root()


@pytest.fixture(scope="module")
def conformance_config() -> dict[str, Any]:
    return _conformance_config()


@pytest.fixture(scope="module")
def method_ids() -> list[str]:
    return _method_ids_from_policy()


@pytest.fixture
def minimal_policy() -> dict[str, Any]:
    return _minimal_policy()


@pytest.fixture
def minimal_scale_config() -> dict[str, Any]:
    return _minimal_scale_config()
