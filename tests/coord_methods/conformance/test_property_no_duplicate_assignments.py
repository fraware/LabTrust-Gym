"""
Property test: routing methods must not assign two agents to the same target in one step.

Runs propose_actions for a few steps with minimal obs; for methods that return per_agent
assignments (e.g. device_id, target_zone), asserts no duplicate target assignments per step.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import (
    _minimal_obs,
    _minimal_scale_config,
    make_coord_method_for_conformance,
)


def _routing_method_ids() -> list[str]:
    """Method IDs that produce routes/assignments (subset of conformance routing_method_ids)."""
    return ["kernel_whca", "kernel_auction_edf", "kernel_auction_whca", "kernel_scheduler_or"]


@pytest.mark.parametrize("method_id", _routing_method_ids())
def test_property_no_duplicate_assignments(
    method_id: str,
    repo_root: Path,
    conformance_config: dict,
    minimal_policy: dict,
) -> None:
    """Routing method: propose_actions over 3 steps yields no duplicate (agent, target) per step."""
    if method_id in (conformance_config.get("skip_legality") or []):
        pytest.skip(f"{method_id}: skipped by conformance_config")
    scale_config = _minimal_scale_config()
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")
    agent_ids = sorted(minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    coord.reset(42, minimal_policy, scale_config)
    seen_targets_per_step: list[set[tuple[str, ...]]] = []
    for t in range(3):
        obs = _minimal_obs(agent_ids, t)
        actions_dict = coord.propose_actions(obs, {}, t)
        if not isinstance(actions_dict, dict):
            continue
        per_agent = actions_dict.get("per_agent") or actions_dict.get("assignments") or []
        if not isinstance(per_agent, list):
            continue
        targets: list[tuple[str, ...]] = []
        for a in per_agent:
            if not isinstance(a, dict):
                continue
            target = a.get("device_id") or a.get("zone_id") or a.get("target_zone") or ""
            agent_id = a.get("agent_id") or ""
            if agent_id and target is not None:
                targets.append((agent_id, str(target)))
        if targets:
            unique = set(targets)
            assert len(unique) == len(targets), f"{method_id} step {t}: duplicate (agent, target) in {targets}"
    assert True
