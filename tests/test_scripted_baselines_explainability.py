"""
Test that scripted baselines always emit reason_code and rationale in action_info.

Guards against regression dropping explainability (aligned with LLM/MARL audit).
"""

from __future__ import annotations

from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
from labtrust_gym.baselines.scripted_runner import (
    DEFAULT_ZONE_IDS,
    ScriptedRunnerAgent,
)
from labtrust_gym.engine.zones import _default_layout as _layout
from labtrust_gym.engine.zones import build_adjacency_set, get_default_device_zone_map


def _ops_obs(
    releasable_result_ids: list | None = None,
    log_frozen: int = 0,
    door_restricted_open: int = 0,
    door_restricted_duration_s: float = 0.0,
    work_list: list | None = None,
    token_count_override: int = 0,
    device_qc_pass: list | None = None,
    queue_lengths: list | None = None,
) -> dict:
    obs: dict = {
        "log_frozen": log_frozen,
        "door_restricted_open": door_restricted_open,
        "door_restricted_duration_s": door_restricted_duration_s,
        "work_list": work_list or [],
        "token_count_override": token_count_override,
        "token_count_restricted": 0,
    }
    if releasable_result_ids is not None:
        obs["releasable_result_ids"] = releasable_result_ids
    if device_qc_pass is not None:
        obs["device_qc_pass"] = device_qc_pass
    if queue_lengths is not None:
        obs["queue_lengths"] = queue_lengths
    return obs


def _runner_obs(
    my_zone_idx: int = 1,
    log_frozen: int = 0,
    door_restricted_open: int = 0,
    door_restricted_duration_s: float = 0.0,
    queue_has_head: list | None = None,
) -> dict:
    obs: dict = {
        "my_zone_idx": my_zone_idx,
        "log_frozen": log_frozen,
        "restricted_zone_frozen": 0,
        "door_restricted_open": door_restricted_open,
        "door_restricted_duration_s": door_restricted_duration_s,
        "token_count_restricted": 1,
    }
    if queue_has_head is not None:
        obs["queue_has_head"] = queue_has_head
    return obs


def test_scripted_ops_action_info_has_reason_code_and_rationale() -> None:
    """Every ScriptedOpsAgent return has reason_code and non-empty rationale."""
    agent = ScriptedOpsAgent()

    cases = [
        (_ops_obs(releasable_result_ids=["R1"]), "release"),
        (
            _ops_obs(
                log_frozen=1,
                work_list=[
                    {
                        "work_id": "W",
                        "priority": "STAT",
                        "deadline_s": 0,
                        "stability_ok": True,
                        "temp_ok": True,
                        "device_id": 0,
                    }
                ],
            ),
            "log_frozen",
        ),
        (_ops_obs(door_restricted_open=1, door_restricted_duration_s=200.0, work_list=[]), "door_tick"),
        (
            _ops_obs(
                work_list=[
                    {
                        "work_id": "W",
                        "priority": "STAT",
                        "deadline_s": 0,
                        "stability_ok": True,
                        "temp_ok": True,
                        "device_id": 0,
                    }
                ],
                queue_lengths=[0] * 6,
                device_qc_pass=[1] * 6,
            ),
            "queue_run",
        ),
        (_ops_obs(work_list=[]), "noop"),
    ]
    for obs, label in cases:
        _idx, action_info = agent.act(obs, "ops_0")
        assert "reason_code" in action_info, f"ops branch {label}: missing reason_code"
        assert "rationale" in action_info, f"ops branch {label}: missing rationale"
        assert isinstance(action_info["rationale"], str) and len(action_info["rationale"]) > 0, (
            f"ops branch {label}: rationale must be non-empty string, got {action_info.get('rationale')!r}"
        )


def test_scripted_runner_action_info_has_reason_code_and_rationale() -> None:
    """Every ScriptedRunnerAgent return has reason_code and non-empty rationale."""
    agent = ScriptedRunnerAgent(zone_ids=DEFAULT_ZONE_IDS)

    # Branches: log_frozen, door_tick, unknown_zone (my_zone_idx 0), at_goal, no_path, move
    zone_ids = DEFAULT_ZONE_IDS
    adjacency = build_adjacency_set(_layout().get("graph_edges", []))
    device_zone = get_default_device_zone_map()
    device_ids = list(device_zone.keys())
    # my_zone_idx 1 = Z_SRA_RECEPTION; pick a zone with a neighbor so MOVE is possible
    sorting_idx = 1 + zone_ids.index("Z_SORTING_LANES") if "Z_SORTING_LANES" in zone_ids else 2

    cases = [
        (_runner_obs(my_zone_idx=1, log_frozen=1), "log_frozen"),
        (_runner_obs(my_zone_idx=1, door_restricted_open=1, door_restricted_duration_s=200.0), "door_tick"),
        (_runner_obs(my_zone_idx=0), "unknown_zone"),
        (_runner_obs(my_zone_idx=sorting_idx, queue_has_head=[0] * len(device_ids)), "at_goal_or_no_path"),
    ]
    for obs, label in cases:
        _idx, action_info = agent.act(obs, "runner_0")
        assert "reason_code" in action_info, f"runner branch {label}: missing reason_code"
        assert "rationale" in action_info, f"runner branch {label}: missing rationale"
        assert isinstance(action_info["rationale"], str) and len(action_info["rationale"]) > 0, (
            f"runner branch {label}: rationale must be non-empty string, got {action_info.get('rationale')!r}"
        )


def test_scripted_runner_move_and_start_run_have_rationale() -> None:
    """Runner MOVE and START_RUN branches include rationale."""
    agent = ScriptedRunnerAgent(zone_ids=DEFAULT_ZONE_IDS)
    device_zone = get_default_device_zone_map()
    device_ids = list(device_zone.keys())
    zone_ids = DEFAULT_ZONE_IDS
    # In ANALYZER_HALL_A with queue_has_head for first device there -> START_RUN
    try:
        hall_a = next(z for z in zone_ids if "ANALYZER" in z)
    except StopIteration:
        hall_a = zone_ids[6] if len(zone_ids) > 6 else zone_ids[-1]
    hall_idx = 1 + zone_ids.index(hall_a)
    queue_has_head = [0] * len(device_ids)
    try:
        dev_idx = next(i for i, did in enumerate(device_ids) if device_zone.get(did) == hall_a)
        queue_has_head[dev_idx] = 1
    except StopIteration:
        queue_has_head[0] = 1
    obs = _runner_obs(my_zone_idx=hall_idx, queue_has_head=queue_has_head)
    _idx, action_info = agent.act(obs, "runner_0")
    assert "rationale" in action_info and len(action_info["rationale"]) > 0
    assert "reason_code" in action_info
