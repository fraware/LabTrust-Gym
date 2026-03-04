"""
Conformance contract: Safety invariants (routing).
For methods that produce routes: no node-time collisions (INV-ROUTE-001),
no illegal restricted edges (INV-ROUTE-002), no swap collision (INV-ROUTE-SWAP).
Methods that do not expose planned path are skipped (by routing_method_ids).
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.routing.invariants import (
    check_inv_route_001,
    check_inv_route_002,
    check_swap_collision,
)

from .conftest import (
    _method_ids_from_policy,
    make_coord_method_for_conformance,
)


def _minimal_obs_distinct_zones(agent_ids: list[str], policy: dict) -> dict:
    """Obs with one zone per agent so INV-ROUTE-001 (no same node at same t) can pass at t=0."""
    inner = policy.get("zone_layout") or policy
    inner = inner.get("zone_layout_policy") or inner
    zone_list = inner.get("zones") or []
    zone_ids = [z.get("zone_id") for z in zone_list if isinstance(z, dict) and z.get("zone_id")]
    if len(zone_ids) < len(agent_ids):
        zone_ids = (
            zone_ids + ["Z_SORTING_LANES", "Z_ANALYZER_HALL_A", "Z_ANALYZER_HALL_B"][: len(agent_ids) - len(zone_ids)]
        )
    obs = {}
    for i, aid in enumerate(agent_ids):
        zid = zone_ids[i % len(zone_ids)]
        obs[aid] = {
            "my_zone_idx": 1 + (i % 2),
            "zone_id": zid,
            "queue_has_head": [0] * 2,
            "queue_by_device": [{"queue_head": "", "queue_len": 0}, {"queue_head": "", "queue_len": 0}],
            "log_frozen": 0,
        }
    return obs


def _get_planned_from_method(method, method_id: str, obs, infos, t: int, scale_config: dict | None = None):
    """
    If the method exposes a planned path via get_last_planned_path() after step/propose_actions,
    return (planned_nodes, planned_moves, restricted_edges, agent_has_token). Otherwise return None.
    """
    get_path = getattr(method, "get_last_planned_path", None)
    if get_path is None or not callable(get_path):
        return None
    return get_path()


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_safety_invariants_contract(
    method_id: str,
    repo_root,
    conformance_config,
    minimal_policy,
    minimal_scale_config,
) -> None:
    """Routing methods: INV-ROUTE-001, INV-ROUTE-002, INV-ROUTE-SWAP on planned path if exposed."""
    routing_ids = conformance_config.get("routing_method_ids") or []
    if method_id not in routing_ids:
        pytest.skip(f"{method_id}: not a routing method (no planned path check)")
    if method_id in (conformance_config.get("skip_safety_invariants") or []):
        pytest.skip(f"{method_id}: skipped by conformance_config")

    scale_config = dict(minimal_scale_config)
    scale_config["expose_planned_path"] = True
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")

    agent_ids = list(minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs_distinct_zones(agent_ids, minimal_policy)
    infos: dict = {}
    coord.reset(42, minimal_policy, scale_config)
    coord.propose_actions(obs, infos, 0)
    planned = _get_planned_from_method(coord, method_id, obs, infos, 0, scale_config)
    if planned is None:
        pytest.skip(f"{method_id}: does not expose planned path (extend interface to run this contract)")

    planned_nodes, planned_moves, restricted_edges, agent_has_token = planned
    v001 = check_inv_route_001(planned_nodes)
    v002 = check_inv_route_002(planned_moves, restricted_edges, agent_has_token)
    v003 = check_swap_collision(planned_moves)
    assert not v001, f"{method_id}: INV-ROUTE-001 violations: {v001}"
    assert not v002, f"{method_id}: INV-ROUTE-002 violations: {v002}"
    assert not v003, f"{method_id}: INV-ROUTE-SWAP violations: {v003}"


def test_swap_collision_helper_unit() -> None:
    """Unit test: check_swap_collision detects A->B and B->A at same t."""
    moves = [
        ("a", 0, "Z1", "Z2"),
        ("b", 0, "Z2", "Z1"),
    ]
    v = check_swap_collision(moves)
    assert len(v) == 1
    assert "swap collision" in v[0].lower() or "INV-ROUTE-SWAP" in v[0]
    moves_ok = [("a", 0, "Z1", "Z2"), ("b", 1, "Z2", "Z1")]
    assert not check_swap_collision(moves_ok)
