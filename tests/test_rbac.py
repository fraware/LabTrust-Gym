"""
Unit tests for RBAC policy: action denied/allowed, device restricted, zone restricted.

Golden GS-RBAC-028 (unauthorized RELEASE_RESULT blocked) and GS-RBAC-029 (token cannot bypass RBAC)
are run by test_golden_suite when LABTRUST_RUN_GOLDEN=1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.engine.rbac import (
    RBAC_ACTION_DENY,
    RBAC_DEVICE_DENY,
    RBAC_ZONE_DENY,
    check,
    get_agent_role,
    load_rbac_policy,
)


def test_load_rbac_policy() -> None:
    path = Path("policy/rbac/rbac_policy.v0.1.yaml")
    if not path.exists():
        pytest.skip("policy/rbac/rbac_policy.v0.1.yaml not found")
    policy = load_rbac_policy(path)
    assert "version" in policy
    assert "roles" in policy
    assert "agents" in policy
    assert policy["agents"].get("A_RECEPTION") == "ROLE_RECEPTION"
    assert policy["agents"].get("A_ANALYTICS") == "ROLE_ANALYTICS"
    assert "RELEASE_RESULT" not in policy["roles"]["ROLE_RECEPTION"]["allowed_actions"]
    assert "RELEASE_RESULT" in policy["roles"]["ROLE_ANALYTICS"]["allowed_actions"]


def test_action_denied_reception_release_result() -> None:
    path = Path("policy/rbac/rbac_policy.v0.1.yaml")
    if not path.exists():
        pytest.skip("policy/rbac/rbac_policy.v0.1.yaml not found")
    policy = load_rbac_policy(path)
    allowed, reason, decision = check(
        "A_RECEPTION",
        "RELEASE_RESULT",
        {},
        policy,
    )
    assert allowed is False
    assert reason == RBAC_ACTION_DENY
    assert decision.get("reason_code") == RBAC_ACTION_DENY
    assert decision.get("role_id") == "ROLE_RECEPTION"


def test_action_allowed_analytics_release_result() -> None:
    path = Path("policy/rbac/rbac_policy.v0.1.yaml")
    if not path.exists():
        pytest.skip("policy/rbac/rbac_policy.v0.1.yaml not found")
    policy = load_rbac_policy(path)
    allowed, reason, decision = check(
        "A_ANALYTICS",
        "RELEASE_RESULT",
        {},
        policy,
    )
    assert allowed is True
    assert reason is None
    assert decision.get("allowed") is True


def test_runner_release_result_override_denied() -> None:
    path = Path("policy/rbac/rbac_policy.v0.1.yaml")
    if not path.exists():
        pytest.skip("policy/rbac/rbac_policy.v0.1.yaml not found")
    policy = load_rbac_policy(path)
    allowed, reason, _ = check(
        "A_RUNNER",
        "RELEASE_RESULT_OVERRIDE",
        {},
        policy,
    )
    assert allowed is False
    assert reason == RBAC_ACTION_DENY


def test_zone_restricted_deny() -> None:
    policy = {
        "version": "0.1",
        "roles": {
            "ROLE_A": {
                "allowed_actions": ["MOVE"],
                "allowed_zones": ["Z_ONLY"],
            },
        },
        "agents": {"AGENT_1": "ROLE_A"},
        "action_constraints": {},
    }
    allowed, reason, _ = check(
        "AGENT_1",
        "MOVE",
        {"zone_id": "Z_OTHER"},
        policy,
    )
    assert allowed is False
    assert reason == RBAC_ZONE_DENY


def test_zone_restricted_allow() -> None:
    policy = {
        "version": "0.1",
        "roles": {
            "ROLE_A": {
                "allowed_actions": ["MOVE"],
                "allowed_zones": ["Z_ONLY"],
            },
        },
        "agents": {"AGENT_1": "ROLE_A"},
        "action_constraints": {},
    }
    allowed, reason, _ = check(
        "AGENT_1",
        "MOVE",
        {"zone_id": "Z_ONLY"},
        policy,
    )
    assert allowed is True
    assert reason is None


def test_device_restricted_deny() -> None:
    policy = {
        "version": "0.1",
        "roles": {
            "ROLE_A": {
                "allowed_actions": ["START_RUN"],
                "allowed_devices": ["DEV_1"],
            },
        },
        "agents": {"AGENT_1": "ROLE_A"},
        "action_constraints": {},
    }
    allowed, reason, _ = check(
        "AGENT_1",
        "START_RUN",
        {"device_id": "DEV_2"},
        policy,
    )
    assert allowed is False
    assert reason == RBAC_DEVICE_DENY


def test_agent_not_in_policy_allowed_backward_compat() -> None:
    policy = {
        "version": "0.1",
        "roles": {"ROLE_A": {"allowed_actions": ["MOVE"]}},
        "agents": {"AGENT_1": "ROLE_A"},
        "action_constraints": {},
    }
    allowed, reason, _ = check(
        "UNKNOWN_AGENT",
        "MOVE",
        {},
        policy,
    )
    assert allowed is True
    assert reason is None


def test_get_agent_role() -> None:
    policy = {
        "version": "0.1",
        "roles": {},
        "agents": {"A_RECEPTION": "ROLE_RECEPTION"},
        "action_constraints": {},
    }
    assert get_agent_role("A_RECEPTION", policy) == "ROLE_RECEPTION"
    assert get_agent_role("UNKNOWN", policy) is None
    assert get_agent_role("A_RECEPTION", {}) is None


def test_gs_rbac_028_reception_release_blocked() -> None:
    """GS-RBAC-028: A_RECEPTION RELEASE_RESULT => BLOCKED RBAC_ACTION_DENY."""
    from labtrust_gym.engine.core_env import CoreEnv

    if not Path("policy/rbac/rbac_policy.v0.1.yaml").exists():
        pytest.skip("rbac_policy not found")
    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [],
        "tokens": [],
        "agents": [{"agent_id": "A_RECEPTION", "zone_id": "Z_SRA_RECEPTION"}],
    }
    env.reset(initial_state, deterministic=True, rng_seed=12345)
    event = {
        "event_id": "e1",
        "t_s": 10000,
        "agent_id": "A_RECEPTION",
        "action_type": "RELEASE_RESULT",
        "args": {"result_id": "RES_ANY"},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert result["status"] == "BLOCKED"
    assert result["blocked_reason_code"] == "RBAC_ACTION_DENY"
    assert result.get("rbac_decision", {}).get("allowed") is False


def test_gs_rbac_029_runner_override_blocked_with_token() -> None:
    """GS-RBAC-029: A_RUNNER RELEASE_RESULT_OVERRIDE with token => BLOCKED RBAC_ACTION_DENY (token cannot bypass)."""
    from labtrust_gym.engine.core_env import CoreEnv

    if not Path("policy/rbac/rbac_policy.v0.1.yaml").exists():
        pytest.skip("rbac_policy not found")
    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [],
        "tokens": [],
        "agents": [{"agent_id": "A_RUNNER", "zone_id": "Z_SORTING_LANES"}],
    }
    env.reset(initial_state, deterministic=True, rng_seed=12345)
    event = {
        "event_id": "e1",
        "t_s": 10010,
        "agent_id": "A_RUNNER",
        "action_type": "RELEASE_RESULT_OVERRIDE",
        "args": {"result_id": "RES_ANY", "reason_code": "TIME_EXPIRED"},
        "reason_code": "TIME_EXPIRED",
        "token_refs": ["T_OVR_FAKE"],
    }
    result = env.step(event)
    assert result["status"] == "BLOCKED"
    assert result["blocked_reason_code"] == "RBAC_ACTION_DENY"
    assert result.get("rbac_decision", {}).get("allowed") is False
