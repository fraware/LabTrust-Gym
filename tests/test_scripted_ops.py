"""
Tests for ScriptedOpsAgent: STAT/EDF policy, determinism, conservative behavior.

Uses synthetic observations; no env required. Verifies action choice is stable
and respects STAT front-of-line, then EDF on deadline_s.
"""

from __future__ import annotations

from labtrust_gym.baselines.scripted_ops import (
    ACTION_NOOP,
    ACTION_QUEUE_RUN,
    ACTION_TICK,
    ScriptedOpsAgent,
)


def _base_obs(
    log_frozen: int = 0,
    door_restricted_open: int = 0,
    door_restricted_duration_s: float = 0.0,
    work_list: list | None = None,
    token_count_override: int = 0,
    token_count_restricted: int = 0,
    device_qc_pass: list | None = None,
    queue_lengths: list | None = None,
) -> dict:
    obs: dict = {
        "log_frozen": log_frozen,
        "door_restricted_open": door_restricted_open,
        "door_restricted_duration_s": door_restricted_duration_s,
        "work_list": work_list or [],
        "token_count_override": token_count_override,
        "token_count_restricted": token_count_restricted,
    }
    if device_qc_pass is not None:
        obs["device_qc_pass"] = device_qc_pass
    if queue_lengths is not None:
        obs["queue_lengths"] = queue_lengths
    return obs


def test_scripted_ops_stat_first() -> None:
    """STAT specimen is chosen before ROUTINE (front-of-line)."""
    agent = ScriptedOpsAgent()
    work_list = [
        {
            "work_id": "R1",
            "priority": "ROUTINE",
            "deadline_s": 100,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": 0,
        },
        {
            "work_id": "S1",
            "priority": "STAT",
            "deadline_s": 200,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": 0,
        },
    ]
    obs = _base_obs(work_list=work_list)
    action_idx, action_info = agent.act(obs, "ops_0")
    assert action_idx == ACTION_QUEUE_RUN
    assert action_info.get("work_id") == "S1"
    assert action_info.get("priority") == "STAT"


def test_scripted_ops_edf_after_stat() -> None:
    """Among non-STAT, earliest deadline first (EDF)."""
    agent = ScriptedOpsAgent()
    work_list = [
        {
            "work_id": "R2",
            "priority": "ROUTINE",
            "deadline_s": 500,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": 0,
        },
        {
            "work_id": "R1",
            "priority": "ROUTINE",
            "deadline_s": 100,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": 0,
        },
    ]
    obs = _base_obs(work_list=work_list)
    action_idx, action_info = agent.act(obs, "ops_0")
    assert action_idx == ACTION_QUEUE_RUN
    assert action_info.get("work_id") == "R1"  # EDF: earlier deadline first


def test_scripted_ops_log_frozen_noop() -> None:
    """When log_frozen=1, agent returns NOOP."""
    agent = ScriptedOpsAgent()
    obs = _base_obs(
        log_frozen=1,
        work_list=[
            {
                "work_id": "W1",
                "priority": "STAT",
                "deadline_s": 100,
                "stability_ok": True,
                "temp_ok": True,
                "device_id": 0,
            }
        ],
    )
    action_idx, _ = agent.act(obs, "ops_0")
    assert action_idx == ACTION_NOOP


def test_scripted_ops_door_open_long_tick() -> None:
    """When restricted door open and duration >= threshold, agent returns TICK."""
    agent = ScriptedOpsAgent(door_tick_threshold_s=100.0)
    obs = _base_obs(
        door_restricted_open=1,
        door_restricted_duration_s=150.0,
        work_list=[
            {
                "work_id": "W1",
                "priority": "STAT",
                "deadline_s": 100,
                "stability_ok": True,
                "temp_ok": True,
                "device_id": 0,
            }
        ],
    )
    action_idx, _ = agent.act(obs, "ops_0")
    assert action_idx == ACTION_TICK


def test_scripted_ops_empty_work_list_noop() -> None:
    """Empty work_list yields NOOP."""
    agent = ScriptedOpsAgent()
    obs = _base_obs(work_list=[])
    action_idx, _ = agent.act(obs, "ops_0")
    assert action_idx == ACTION_NOOP


def test_scripted_ops_determinism() -> None:
    """Same observation twice yields identical (action_idx, action_info)."""
    agent = ScriptedOpsAgent()
    work_list = [
        {
            "work_id": "S1",
            "priority": "STAT",
            "deadline_s": 100,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": 0,
        },
    ]
    obs = _base_obs(work_list=work_list)
    a1, i1 = agent.act(obs, "ops_0")
    a2, i2 = agent.act(obs, "ops_0")
    assert a1 == a2
    assert i1 == i2


def test_scripted_ops_conservative_hold_without_override() -> None:
    """Work with stability_ok=False and no override token is not queued (hold)."""
    agent = ScriptedOpsAgent(request_override_if_configured=False)
    work_list = [
        {
            "work_id": "W1",
            "priority": "ROUTINE",
            "deadline_s": 100,
            "stability_ok": False,
            "temp_ok": True,
            "device_id": 0,
        },
    ]
    obs = _base_obs(work_list=work_list, token_count_override=0)
    action_idx, _ = agent.act(obs, "ops_0")
    assert action_idx == ACTION_NOOP


def test_scripted_ops_qc_fail_route_alternate() -> None:
    """If primary device QC fail, agent routes to alternate when compatible."""
    # Device 0 = CHEM_A (index 2 in DEFAULT_DEVICE_IDS), alternate CHEM_B (index 3)
    agent = ScriptedOpsAgent()
    work_list = [
        {
            "work_id": "W1",
            "priority": "STAT",
            "deadline_s": 100,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": 2,
        },
    ]
    # device_qc_pass: index 2 (CHEM_A) fail, index 3 (CHEM_B) pass
    obs = _base_obs(
        work_list=work_list,
        device_qc_pass=[1, 1, 0, 1, 1, 1],
        queue_lengths=[0, 0, 0, 0, 0, 0],
    )
    action_idx, action_info = agent.act(obs, "ops_0")
    assert action_idx == ACTION_QUEUE_RUN
    # Should route to alternate (DEV_CHEM_B_01)
    assert action_info.get("device_id") == "DEV_CHEM_B_01"


def test_scripted_ops_qc_fail_no_alternate_hold() -> None:
    """If device QC fail and no alternate has QC pass, hold (skip that work)."""
    agent = ScriptedOpsAgent()
    work_list = [
        {
            "work_id": "W1",
            "priority": "STAT",
            "deadline_s": 100,
            "stability_ok": True,
            "temp_ok": True,
            "device_id": 0,
        },
    ]
    # All devices fail QC
    obs = _base_obs(
        work_list=work_list,
        device_qc_pass=[0, 0, 0, 0, 0, 0],
        queue_lengths=[0, 0, 0, 0, 0, 0],
    )
    action_idx, _ = agent.act(obs, "ops_0")
    assert action_idx == ACTION_NOOP
