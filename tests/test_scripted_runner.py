"""
Tests for ScriptedRunnerAgent: legal MOVE (graph edges), START_RUN only when
colocated. Uses synthetic observations; verifies the agent never proposes
illegal MOVE and never proposes START_RUN when not in the device zone.
"""

from __future__ import annotations

from labtrust_gym.baselines.scripted_runner import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_START_RUN,
    ACTION_TICK,
    DEFAULT_ZONE_IDS,
    ScriptedRunnerAgent,
)
from labtrust_gym.engine.zones import _default_layout as _layout
from labtrust_gym.engine.zones import (
    build_adjacency_set,
    get_default_device_zone_map,
)


def _adjacency() -> set:
    return build_adjacency_set(_layout().get("graph_edges", []))


def _device_zone_map():
    return get_default_device_zone_map()


def _obs(
    my_zone_idx: int,
    log_frozen: int = 0,
    restricted_zone_frozen: int = 0,
    door_restricted_open: int = 0,
    door_restricted_duration_s: float = 0.0,
    queue_has_head: list | None = None,
    token_count_restricted: int = 0,
) -> dict:
    """Build observation dict for runner (minimal fields)."""
    obs = {
        "my_zone_idx": my_zone_idx,
        "log_frozen": log_frozen,
        "restricted_zone_frozen": restricted_zone_frozen,
        "door_restricted_open": door_restricted_open,
        "door_restricted_duration_s": door_restricted_duration_s,
        "token_count_restricted": token_count_restricted,
    }
    if queue_has_head is not None:
        obs["queue_has_head"] = queue_has_head
    return obs


def test_scripted_runner_never_proposes_illegal_move() -> None:
    """For any obs, if agent returns MOVE, (my_zone, to_zone) must be a graph edge."""
    agent = ScriptedRunnerAgent(zone_ids=DEFAULT_ZONE_IDS)
    adjacency = _adjacency()
    zone_ids = DEFAULT_ZONE_IDS

    for idx in range(1, len(zone_ids) + 1):
        my_zone = zone_ids[idx - 1]
        obs = _obs(my_zone_idx=idx, queue_has_head=[0] * 6)
        action_idx, action_info = agent.act(obs, "runner_0")
        if action_idx == ACTION_MOVE:
            to_zone = action_info.get("to_zone", "")
            assert (my_zone, to_zone) in adjacency, f"MOVE from {my_zone} to {to_zone} is not a legal edge"


def test_scripted_runner_never_start_run_when_not_colocated() -> None:
    """If agent returns START_RUN, my_zone must equal device_zone for device."""
    agent = ScriptedRunnerAgent(zone_ids=DEFAULT_ZONE_IDS)
    device_zone = _device_zone_map()
    zone_ids = DEFAULT_ZONE_IDS
    device_ids = list(device_zone.keys())

    for zone_idx, my_zone in enumerate(zone_ids, start=1):
        for dev_idx, dev_id in enumerate(device_ids):
            dev_zone = device_zone.get(dev_id)
            if dev_zone is None:
                continue
            queue_has_head = [0] * len(device_ids)
            queue_has_head[dev_idx] = 1
            obs = _obs(
                my_zone_idx=zone_idx,
                queue_has_head=queue_has_head,
            )
            action_idx, action_info = agent.act(obs, "runner_0")
            if action_idx == ACTION_START_RUN:
                device_id = action_info.get("device_id", "")
                assert my_zone == device_zone.get(device_id), (
                    f"START_RUN for device {device_id} from zone {my_zone} "
                    f"(device zone is {device_zone.get(device_id)})"
                )


def test_scripted_runner_log_frozen_noop() -> None:
    """When log_frozen=1, agent returns NOOP."""
    agent = ScriptedRunnerAgent(zone_ids=DEFAULT_ZONE_IDS)
    obs = _obs(
        my_zone_idx=1,
        log_frozen=1,
        queue_has_head=[1, 0, 0, 0, 0, 0],
    )
    action_idx, _ = agent.act(obs, "runner_0")
    assert action_idx == ACTION_NOOP


def test_scripted_runner_door_open_long_tick() -> None:
    """When restricted door open and duration >= threshold, agent returns TICK."""
    agent = ScriptedRunnerAgent(
        zone_ids=DEFAULT_ZONE_IDS,
        door_tick_threshold_s=100.0,
    )
    obs = _obs(
        my_zone_idx=1,
        door_restricted_open=1,
        door_restricted_duration_s=150.0,
        queue_has_head=[0] * 6,
    )
    action_idx, _ = agent.act(obs, "runner_0")
    assert action_idx == ACTION_TICK


def test_scripted_runner_colocated_start_run() -> None:
    """In device zone with queue head, agent returns START_RUN."""
    agent = ScriptedRunnerAgent(zone_ids=DEFAULT_ZONE_IDS)
    device_zone = _device_zone_map()
    device_ids = list(device_zone.keys())
    dev_zone = device_zone.get("DEV_CHEM_A_01")
    assert dev_zone is not None
    my_zone_idx = DEFAULT_ZONE_IDS.index(dev_zone) + 1
    dev_idx = device_ids.index("DEV_CHEM_A_01")
    queue_has_head = [0] * len(device_ids)
    queue_has_head[dev_idx] = 1
    obs = _obs(my_zone_idx=my_zone_idx, queue_has_head=queue_has_head)
    action_idx, action_info = agent.act(obs, "runner_0")
    assert action_idx == ACTION_START_RUN
    assert action_info.get("device_id") == "DEV_CHEM_A_01"


def test_scripted_runner_determinism() -> None:
    """Same observation yields same (action_idx, action_info)."""
    agent = ScriptedRunnerAgent(zone_ids=DEFAULT_ZONE_IDS)
    obs = _obs(my_zone_idx=1, queue_has_head=[0] * 6)
    a1, i1 = agent.act(obs, "runner_0")
    a2, i2 = agent.act(obs, "runner_0")
    assert a1 == a2
    assert i1 == i2
