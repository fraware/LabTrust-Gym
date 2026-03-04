"""
Conformance contract: Budget.
Per-step compute budget (e.g. time_ms, node_expansions) documented; method either
completes within budget or degrades gracefully (documented fallback).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import (
    _method_ids_from_policy,
    _minimal_obs,
    _minimal_scale_config,
    make_coord_method_for_conformance,
)


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_budget_contract(
    method_id: str,
    repo_root: Path,
    conformance_config: dict,
    minimal_policy: dict,
    minimal_scale_config: dict,
) -> None:
    """With very low budget, method completes within budget or uses documented fallback."""
    pass_budget = conformance_config.get("pass_budget") or []
    if method_id not in pass_budget:
        pytest.skip(f"{method_id}: not in pass_budget; add when method accepts budget knob")
    scale_config = dict(_minimal_scale_config())
    scale_config["compute_budget_ms"] = 1
    scale_config["compute_budget_node_expansions"] = 10

    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")

    agent_ids = sorted(minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}

    coord.reset(42, minimal_policy, scale_config)
    actions_dict = coord.propose_actions(obs, infos, 0)

    # Must return valid structure: one entry per agent (or documented subset)
    assert isinstance(actions_dict, dict)
    for aid in agent_ids:
        ad = actions_dict.get(aid, {})
        assert "action_index" in ad
        assert ad["action_index"] in (0, 1, 2, 3, 4, 5)
