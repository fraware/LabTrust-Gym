"""
MAPF property tests for kernel_whca: collision-free paths (INV-ROUTE-001, no swap).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.registry import make_coordination_method


def _three_zone_line_policy() -> dict:
    """Z_A -- Z_B -- Z_C; device in Z_B."""
    return {
        "zone_layout": {
            "zones": [{"zone_id": "Z_A"}, {"zone_id": "Z_B"}, {"zone_id": "Z_C"}],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_B"}],
            "graph_edges": [
                {"from": "Z_A", "to": "Z_B"},
                {"from": "Z_B", "to": "Z_A"},
                {"from": "Z_B", "to": "Z_C"},
                {"from": "Z_C", "to": "Z_B"},
            ],
        },
        "pz_to_engine": {"a1": "ops_0", "a2": "runner_0"},
    }


def _obs_two_agents_crossing_to_b() -> dict:
    """a1 in Z_A, a2 in Z_C; both have work at D1 in Z_B so both route to Z_B."""
    return {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [{"queue_len": 1, "queue_head": "W1"}],
            "queue_has_head": [1],
            "log_frozen": 0,
        },
        "a2": {
            "zone_id": "Z_C",
            "queue_by_device": [{"queue_len": 1, "queue_head": "W2"}],
            "queue_has_head": [1],
            "log_frozen": 0,
        },
    }


def _check_inv_route_001_no_duplicate_node_time(
    planned_nodes: list[tuple[str, int, str]],
) -> list[str]:
    """INV-ROUTE-001: at most one agent per (t, node). Returns list of violations."""
    violations = []
    seen: dict[tuple[int, str], str] = {}
    for agent_id, t, node in planned_nodes:
        key = (t, node)
        if key in seen and seen[key] != agent_id:
            violations.append(f"collision at (t={t}, node={node}): {seen[key]} and {agent_id}")
        seen[key] = agent_id
    return violations


def _check_no_swap(
    planned_moves: list[tuple[str, int, str, str]],
) -> list[str]:
    """No swap: no (a1,t,A,B) and (a2,t,B,A) for same t."""
    violations = []
    by_t: dict[int, list[tuple[str, str, str]]] = {}
    for agent_id, t, n_from, n_to in planned_moves:
        by_t.setdefault(t, []).append((agent_id, n_from, n_to))
    for t, moves in by_t.items():
        for i, (a1, from1, to1) in enumerate(moves):
            for a2, from2, to2 in moves[i + 1 :]:
                if from1 == to2 and to1 == from2:
                    violations.append(f"swap at t={t}: {a1} ({from1}->{to1}) vs {a2} ({from2}->{to2})")
    return violations


def test_kernel_whca_mapf_collision_free_and_no_swap() -> None:
    """WHCA plans collision-free paths; INV-ROUTE-001 and no swap."""
    repo_root = Path(__file__).resolve().parent.parent
    scale_config = {
        "expose_planned_path": True,
        "seed": 42,
        "num_agents_total": 2,
        "horizon_steps": 15,
    }
    policy = _three_zone_line_policy()
    coord = make_coordination_method(
        "kernel_whca",
        policy,
        repo_root=repo_root,
        scale_config=scale_config,
    )
    if coord is None:
        pytest.skip("kernel_whca not available")
    obs = _obs_two_agents_crossing_to_b()
    coord.reset(seed=42, policy=policy, scale_config=scale_config)
    coord.propose_actions(obs, {}, 0)
    path_result = getattr(coord, "get_last_planned_path", None)
    if path_result is None:
        pytest.skip("kernel_whca does not expose get_last_planned_path")
    result = path_result()
    if result is None:
        pytest.skip("no planned path (expose_planned_path or no routes)")
    planned_nodes, planned_moves, _restricted_edges, _agent_has_token = result
    v001 = _check_inv_route_001_no_duplicate_node_time(planned_nodes)
    v_swap = _check_no_swap(planned_moves)
    assert not v001, v001
    assert not v_swap, v_swap


def _four_zone_line_policy() -> dict:
    """Z_A -- Z_B -- Z_C -- Z_D (line of 4); device in Z_D."""
    return {
        "zone_layout": {
            "zones": [
                {"zone_id": "Z_A"},
                {"zone_id": "Z_B"},
                {"zone_id": "Z_C"},
                {"zone_id": "Z_D"},
            ],
            "device_placement": [{"device_id": "D1", "zone_id": "Z_D"}],
            "graph_edges": [
                {"from": "Z_A", "to": "Z_B"},
                {"from": "Z_B", "to": "Z_A"},
                {"from": "Z_B", "to": "Z_C"},
                {"from": "Z_C", "to": "Z_B"},
                {"from": "Z_C", "to": "Z_D"},
                {"from": "Z_D", "to": "Z_C"},
            ],
        },
        "pz_to_engine": {"a1": "ops_0", "a2": "runner_0"},
    }


def _obs_two_agents_four_zone_line() -> dict:
    """a1 in Z_A, a2 in Z_C; both route toward Z_D."""
    return {
        "a1": {
            "zone_id": "Z_A",
            "queue_by_device": [{"queue_len": 1, "queue_head": "W1"}],
            "queue_has_head": [1],
            "log_frozen": 0,
        },
        "a2": {
            "zone_id": "Z_C",
            "queue_by_device": [{"queue_len": 1, "queue_head": "W2"}],
            "queue_has_head": [1],
            "log_frozen": 0,
        },
    }


def test_kernel_whca_mapf_four_zone_line_collision_free() -> None:
    """WHCA on a 4-zone line graph: collision-free paths (INV-ROUTE-001, no swap)."""
    repo_root = Path(__file__).resolve().parent.parent
    scale_config = {
        "expose_planned_path": True,
        "seed": 123,
        "num_agents_total": 2,
        "horizon_steps": 20,
    }
    policy = _four_zone_line_policy()
    coord = make_coordination_method(
        "kernel_whca",
        policy,
        repo_root=repo_root,
        scale_config=scale_config,
    )
    if coord is None:
        pytest.skip("kernel_whca not available")
    obs = _obs_two_agents_four_zone_line()
    coord.reset(seed=123, policy=policy, scale_config=scale_config)
    coord.propose_actions(obs, {}, 0)
    path_result = getattr(coord, "get_last_planned_path", None)
    if path_result is None:
        pytest.skip("kernel_whca does not expose get_last_planned_path")
    result = path_result()
    if result is None:
        pytest.skip("no planned path")
    planned_nodes, planned_moves, _, _ = result
    v001 = _check_inv_route_001_no_duplicate_node_time(planned_nodes)
    v_swap = _check_no_swap(planned_moves)
    assert not v001, v001
    assert not v_swap, v_swap
