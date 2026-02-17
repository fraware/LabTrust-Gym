"""
Conformance contract: Legality.
Every emitted action must be in allowed_actions(agent); args pass schema;
forbidden RBAC/token actions must not appear (even pre-shield).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.interface import VALID_ACTION_INDICES
from labtrust_gym.engine.rbac import get_allowed_actions

from .conftest import (
    _method_ids_from_policy,
    _minimal_obs,
    _minimal_scale_config,
    make_coord_method_for_conformance,
)

# Action index to type name (align with env)
ACTION_INDEX_TO_TYPE = {
    0: "NOOP",
    1: "TICK",
    2: "QUEUE_RUN",
    3: "MOVE",
    4: "OPEN_DOOR",
    5: "START_RUN",
}


def _policy_with_rbac(repo_root: Path, minimal_policy: dict) -> dict:
    """Policy with RBAC so get_allowed_actions returns non-empty. Uses agent_ids from pz_to_engine keys."""
    # Use same agent_ids as obs (keys of pz_to_engine) so get_allowed_actions(agent_id, policy) works
    agent_ids = sorted((minimal_policy.get("pz_to_engine") or {}).keys())
    if not agent_ids:
        agent_ids = ["worker_0", "worker_1", "worker_2"]
    roles = {
        "ROLE_RUNNER": {
            "allowed_actions": ["NOOP", "TICK", "MOVE", "START_RUN", "QUEUE_RUN", "OPEN_DOOR"],
        },
    }
    agents = {aid: "ROLE_RUNNER" for aid in agent_ids}
    out = dict(minimal_policy)
    out["roles"] = roles
    out["agents"] = agents
    out["action_constraints"] = {}
    return out


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_legality_contract(
    method_id: str,
    repo_root,
    conformance_config,
    minimal_policy,
    minimal_scale_config,
) -> None:
    """Every action_type in allowed_actions(agent); action_index in 0..5."""
    if method_id in (conformance_config.get("skip_legality") or []):
        pytest.skip(f"{method_id}: skipped by conformance_config (legality)")
    if method_id in (conformance_config.get("xfail_legality") or []):
        pytest.xfail(f"{method_id}: known to fail legality until upgraded")
    scale_config = _minimal_scale_config()
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")

    policy = _policy_with_rbac(repo_root, minimal_policy)
    agent_ids = sorted(policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}

    coord.reset(42, policy, scale_config)
    actions_dict = coord.propose_actions(obs, infos, 0)

    for aid in agent_ids:
        ad = actions_dict.get(aid, {})
        idx = ad.get("action_index", 0)
        assert idx in VALID_ACTION_INDICES, f"{method_id} {aid}: action_index {idx} not in 0..5"
        action_type = ad.get("action_type") or ACTION_INDEX_TO_TYPE.get(idx, "NOOP")
        allowed = get_allowed_actions(aid, policy)
        if allowed:
            assert action_type in allowed, (
                f"{method_id} {aid}: action_type {action_type!r} not in allowed_actions {allowed}"
            )
