"""
Load scenario JSON fixtures and build policy/obs/scale_config for scenario tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _scenarios_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "fixtures" / "scenarios"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def load_scenario(scenario_path: Path) -> dict[str, Any]:
    """Load one scenario JSON. Returns dict with policy, scale_config, initial_state, expected."""
    with scenario_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def scenario_to_policy(scenario: dict[str, Any]) -> dict[str, Any]:
    """Build policy dict from scenario.policy (zone_layout, pz_to_engine, roles, agents)."""
    p = scenario.get("policy") or {}
    return {
        "zone_layout": p.get("zone_layout") or {},
        "pz_to_engine": p.get("pz_to_engine") or {},
        "roles": p.get("roles") or {},
        "agents": p.get("agents") or {},
        "action_constraints": p.get("action_constraints") or {},
    }


def scenario_to_scale_config(scenario: dict[str, Any]) -> dict[str, Any]:
    """Build scale_config from scenario.scale_config."""
    sc = scenario.get("scale_config") or {}
    return {
        "num_agents_total": sc.get("num_agents_total", 2),
        "horizon_steps": sc.get("horizon_steps", 10),
        "seed": sc.get("seed", 42),
    }


def scenario_obs_at_step(scenario: dict[str, Any], t: int) -> dict[str, Any]:
    """Build obs dict from scenario initial_state (and optional t)."""
    state = scenario.get("initial_state") or {}
    agent_ids = state.get("agent_ids") or []
    zone_for_agent = state.get("zone_for_agent") or {}
    queue_by_device = state.get("queue_by_device") or []
    frozen_agents = set(state.get("frozen_agents") or [])

    zones_list = []
    zl = (scenario.get("policy") or {}).get("zone_layout") or {}
    for z in zl.get("zones") or []:
        zones_list.append(z.get("zone_id") or "")
    if not zones_list and zone_for_agent:
        zones_list = sorted(set(zone_for_agent.values()))

    obs: dict[str, Any] = {}
    for i, aid in enumerate(agent_ids):
        zone_id = zone_for_agent.get(aid, "Z_A")
        try:
            my_zone_idx = zones_list.index(zone_id) + 1
        except ValueError:
            my_zone_idx = 1
        queue_has_head = [1 if (d.get("queue_head") or "") else 0 for d in queue_by_device]
        if not queue_has_head:
            queue_has_head = [0]
        obs[aid] = {
            "my_zone_idx": my_zone_idx,
            "zone_id": zone_id,
            "queue_has_head": queue_has_head,
            "queue_by_device": queue_by_device or [{"queue_head": "", "queue_len": 0}],
            "log_frozen": 1 if aid in frozen_agents else 0,
        }
    return obs


def list_scenario_paths() -> list[Path]:
    """All scenario JSON paths in tests/fixtures/scenarios/."""
    d = _scenarios_dir()
    if not d.exists():
        return []
    return sorted(d.glob("*.json"))


@pytest.fixture(scope="module")
def scenarios_dir() -> Path:
    return _scenarios_dir()


@pytest.fixture(scope="module")
def scenario_paths() -> list[Path]:
    return list_scenario_paths()


def make_coord_method_for_scenario(
    method_id: str,
    policy: dict[str, Any],
    scale_config: dict[str, Any],
) -> Any | None:
    """Create coordination method for scenario; returns None if optional deps missing."""
    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    repo = _repo_root()
    try:
        if method_id == "llm_constrained":
            pytest.skip("llm_constrained requires LLM agent fixture; skip in scenario harness")
        return make_coordination_method(
            method_id,
            policy,
            repo_root=repo,
            scale_config=scale_config,
        )
    except (ImportError, ValueError, NotImplementedError, RuntimeError) as e:
        if "marl_ppo" in method_id or "stable_baselines3" in str(e).lower():
            return None
        raise
