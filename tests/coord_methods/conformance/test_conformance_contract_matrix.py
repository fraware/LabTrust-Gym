"""
Conformance contract matrix: single entrypoint parametrized over (method_id, contract).

Runs all five contracts (determinism, legality, safety_invariants, budget, evidence)
for each coordination method; skip/xfail controlled by conformance_config.yaml.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import (
    _conformance_config,
    _method_ids_from_policy,
    _minimal_obs,
    _minimal_policy,
    _minimal_scale_config,
    make_coord_method_for_conformance,
)

CONTRACTS = ["determinism", "legality", "safety_invariants", "budget", "evidence"]


def _minimal_obs_distinct_zones(agent_ids, policy):
    """Obs with one zone per agent so INV-ROUTE-001 passes at t=0."""
    inner = policy.get("zone_layout") or policy
    inner = inner.get("zone_layout_policy") or inner
    zone_list = inner.get("zones") or []
    zone_ids = [z.get("zone_id") for z in zone_list if isinstance(z, dict) and z.get("zone_id")]
    if len(zone_ids) < len(agent_ids):
        zone_ids = zone_ids + ["Z_SORTING_LANES", "Z_ANALYZER_HALL_A", "Z_ANALYZER_HALL_B"][: len(agent_ids) - len(zone_ids)]
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


def _run_determinism(repo_root, conformance_config, minimal_policy, method_id: str) -> None:
    if method_id in (conformance_config.get("skip_determinism") or []):
        pytest.skip(f"{method_id}: skipped by conformance_config (determinism)")
    scale_config = _minimal_scale_config(seed=42)
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")
    policy = minimal_policy
    agent_ids = sorted(policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}
    coord.reset(42, policy, scale_config)
    run1 = coord.propose_actions(obs, infos, 0)
    coord.reset(42, policy, scale_config)
    run2 = coord.propose_actions(obs, infos, 0)
    coord.reset(42, policy, scale_config)
    run3 = coord.propose_actions(obs, infos, 0)
    from labtrust_gym.baselines.coordination.interface import VALID_ACTION_INDICES
    for aid in agent_ids:
        a1, a2, a3 = run1.get(aid, {}), run2.get(aid, {}), run3.get(aid, {})
        assert a1.get("action_index") == a2.get("action_index") == a3.get("action_index")
        assert a1.get("action_index") in VALID_ACTION_INDICES
    if conformance_config.get("xfail_determinism") and method_id in conformance_config["xfail_determinism"]:
        pytest.xfail(f"{method_id}: known to fail determinism until upgraded")


def _run_legality(repo_root, conformance_config, minimal_policy, method_id: str) -> None:
    from labtrust_gym.baselines.coordination.interface import VALID_ACTION_INDICES
    from labtrust_gym.engine.rbac import get_allowed_actions
    if method_id in (conformance_config.get("skip_legality") or []):
        pytest.skip(f"{method_id}: skipped by conformance_config (legality)")
    if method_id in (conformance_config.get("xfail_legality") or []):
        pytest.xfail(f"{method_id}: known to fail legality until upgraded")
    scale_config = _minimal_scale_config()
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")
    agent_ids = sorted((minimal_policy.get("pz_to_engine") or {}).keys()) or ["worker_0", "worker_1", "worker_2"]
    roles = {"ROLE_RUNNER": {"allowed_actions": ["NOOP", "TICK", "MOVE", "START_RUN", "QUEUE_RUN", "OPEN_DOOR"]}}
    agents = {aid: "ROLE_RUNNER" for aid in agent_ids}
    policy = dict(minimal_policy)
    policy["roles"] = roles
    policy["agents"] = agents
    policy["action_constraints"] = {}
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}
    coord.reset(42, policy, scale_config)
    actions_dict = coord.propose_actions(obs, infos, 0)
    ACTION_INDEX_TO_TYPE = {0: "NOOP", 1: "TICK", 2: "QUEUE_RUN", 3: "MOVE", 4: "OPEN_DOOR", 5: "START_RUN"}
    for aid in agent_ids:
        ad = actions_dict.get(aid, {})
        idx = ad.get("action_index", 0)
        assert idx in VALID_ACTION_INDICES
        action_type = ad.get("action_type") or ACTION_INDEX_TO_TYPE.get(idx, "NOOP")
        allowed = get_allowed_actions(aid, policy)
        if allowed:
            assert action_type in allowed


def _run_safety_invariants(repo_root, conformance_config, minimal_policy, method_id: str) -> None:
    routing_ids = conformance_config.get("routing_method_ids") or []
    if method_id not in routing_ids:
        pytest.skip(f"{method_id}: not a routing method")
    if method_id in (conformance_config.get("skip_safety_invariants") or []):
        pytest.skip(f"{method_id}: skipped by conformance_config")
    scale_config = dict(_minimal_scale_config())
    scale_config["expose_planned_path"] = True
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")
    agent_ids = list(minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs_distinct_zones(agent_ids, minimal_policy)
    coord.reset(42, minimal_policy, scale_config)
    coord.propose_actions(obs, {}, 0)
    planned = getattr(coord, "get_last_planned_path", None)
    if planned is None or not callable(planned):
        pytest.skip(f"{method_id}: does not expose planned path")
    result = planned()
    if result is None:
        pytest.skip(f"{method_id}: no planned path after step")
    planned_nodes, planned_moves, restricted_edges, agent_has_token = result
    from labtrust_gym.baselines.coordination.routing.invariants import (
        check_inv_route_001,
        check_inv_route_002,
        check_swap_collision,
    )
    v001 = check_inv_route_001(planned_nodes)
    v002 = check_inv_route_002(planned_moves, restricted_edges, agent_has_token)
    v003 = check_swap_collision(planned_moves)
    assert not v001, v001
    assert not v002, v002
    assert not v003, v003


def _run_budget(repo_root, conformance_config, minimal_policy, method_id: str) -> None:
    pass_budget = conformance_config.get("pass_budget") or []
    if method_id not in pass_budget:
        pytest.skip(f"{method_id}: not in pass_budget")
    scale_config = dict(_minimal_scale_config())
    scale_config["compute_budget_ms"] = 1
    scale_config["compute_budget_node_expansions"] = 10
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")
    agent_ids = sorted(minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs(agent_ids, 0)
    coord.reset(42, minimal_policy, scale_config)
    actions_dict = coord.propose_actions(obs, {}, 0)
    assert isinstance(actions_dict, dict)
    for aid in agent_ids:
        ad = actions_dict.get(aid, {})
        assert "action_index" in ad
        assert ad["action_index"] in (0, 1, 2, 3, 4, 5)


def _run_evidence(repo_root, conformance_config, minimal_policy, method_id: str, tmp_path: Path) -> None:
    import json
    from labtrust_gym.baselines.coordination.trace import (
        append_trace_event,
        trace_event_hash,
        trace_from_contract_record,
    )
    pass_evidence = conformance_config.get("pass_evidence") or []
    if method_id not in pass_evidence:
        pytest.skip(f"{method_id}: not in pass_evidence")
    scale_config = _minimal_scale_config()
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")
    agent_ids = sorted(minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs(agent_ids, 0)
    trace_path = tmp_path / "METHOD_TRACE.jsonl"
    coord.reset(42, minimal_policy, scale_config)
    actions_dict = coord.propose_actions(obs, {}, 0)
    event = trace_from_contract_record(method_id, 0, actions_dict)
    append_trace_event(trace_path, event)
    assert trace_path.exists()
    lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    for line in lines:
        parsed = json.loads(line)
        assert parsed.get("method_id") == method_id and "t_step" in parsed and "stage" in parsed
    coord.reset(42, minimal_policy, scale_config)
    actions_dict2 = coord.propose_actions(obs, {}, 0)
    event2 = trace_from_contract_record(method_id, 0, actions_dict2)
    assert trace_event_hash(event) == trace_event_hash(event2)


def _conformance_matrix():
    config = _conformance_config()
    method_ids = _method_ids_from_policy()
    for method_id in method_ids:
        for contract in CONTRACTS:
            yield method_id, contract


@pytest.mark.parametrize("method_id,contract", list(_conformance_matrix()))
def test_conformance_contract(
    method_id: str,
    contract: str,
    repo_root: Path,
    conformance_config: dict,
    minimal_policy: dict,
    tmp_path: Path,
) -> None:
    """Single entrypoint: run the given contract for the given method_id."""
    if contract == "determinism":
        _run_determinism(repo_root, conformance_config, minimal_policy, method_id)
    elif contract == "legality":
        _run_legality(repo_root, conformance_config, minimal_policy, method_id)
    elif contract == "safety_invariants":
        _run_safety_invariants(repo_root, conformance_config, minimal_policy, method_id)
    elif contract == "budget":
        _run_budget(repo_root, conformance_config, minimal_policy, method_id)
    elif contract == "evidence":
        _run_evidence(repo_root, conformance_config, minimal_policy, method_id, tmp_path)
    else:
        pytest.skip(f"Unknown contract: {contract}")
