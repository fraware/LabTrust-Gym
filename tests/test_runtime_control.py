"""
Unit tests for runtime control actions (UPDATE_ROSTER, INJECT_SPECIMEN).

- Runtime control requires SYSTEM agent_id, RBAC allowlist (R_SYSTEM_CONTROL), and valid signature.
- Wrong key or missing signature -> BLOCKED; control_decision in step output and episode log.
- GS-SHIFT-CHANGE-001/002 run in test_golden_suite when LABTRUST_RUN_GOLDEN=1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.engine.signatures import (
    R_SYSTEM_CONTROL_ROLE,
    RUNTIME_CONTROL_ACTION_TYPES,
    SIG_MISSING,
    SIG_ROLE_MISMATCH,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_runtime_control_action_types_frozen() -> None:
    """RUNTIME_CONTROL_ACTION_TYPES includes UPDATE_ROSTER and INJECT_SPECIMEN only."""
    assert "UPDATE_ROSTER" in RUNTIME_CONTROL_ACTION_TYPES
    assert "INJECT_SPECIMEN" in RUNTIME_CONTROL_ACTION_TYPES
    assert len(RUNTIME_CONTROL_ACTION_TYPES) == 2
    assert R_SYSTEM_CONTROL_ROLE == "R_SYSTEM_CONTROL"


def test_runtime_control_missing_signature_blocked() -> None:
    """UPDATE_ROSTER without key_id/signature -> BLOCKED SIG_MISSING; control_decision in output."""
    if os.environ.get("LABTRUST_RUN_GOLDEN") != "1":
        pytest.skip("LABTRUST_RUN_GOLDEN=1 required for engine")
    from labtrust_gym.engine.core_env import CoreEnv

    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [],
    }
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "event_id": "e1",
        "t_s": 700,
        "agent_id": "SYSTEM",
        "action_type": "UPDATE_ROSTER",
        "args": {"roster": {"A_RECEPTION": "ROLE_ANALYTICS", "A_ANALYTICS": "ROLE_RECEPTION"}},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert result["status"] == "BLOCKED"
    assert result.get("blocked_reason_code") == SIG_MISSING
    control = result.get("control_decision")
    assert control is not None
    assert control.get("allowed") is False
    assert control.get("reason_code") == SIG_MISSING
    assert control.get("signature_passed") is False


def test_runtime_control_wrong_key_blocked() -> None:
    """UPDATE_ROSTER with key bound to different agent -> BLOCKED; control_decision present."""
    if os.environ.get("LABTRUST_RUN_GOLDEN") != "1":
        pytest.skip("LABTRUST_RUN_GOLDEN=1 required for engine")
    from labtrust_gym.engine.core_env import CoreEnv

    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [],
    }
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "event_id": "e1",
        "t_s": 700,
        "agent_id": "SYSTEM",
        "key_id": "ed25519:key_analytics",
        "signature": "GOLDEN_TEST_ACCEPT",
        "action_type": "UPDATE_ROSTER",
        "args": {"roster": {"A_RECEPTION": "ROLE_ANALYTICS", "A_ANALYTICS": "ROLE_RECEPTION"}},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert result["status"] == "BLOCKED"
    assert result.get("blocked_reason_code") in ("SIG_INVALID", SIG_ROLE_MISMATCH)
    control = result.get("control_decision")
    assert control is not None
    assert control.get("allowed") is False
    assert control.get("signature_passed") is False or control.get("reason_code") == SIG_ROLE_MISMATCH


def test_runtime_control_system_key_accepted() -> None:
    """UPDATE_ROSTER with SYSTEM key and GOLDEN_TEST_ACCEPT -> ACCEPTED; control_decision ok."""
    if os.environ.get("LABTRUST_RUN_GOLDEN") != "1":
        pytest.skip("LABTRUST_RUN_GOLDEN=1 required for engine")
    from labtrust_gym.engine.core_env import CoreEnv

    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [],
    }
    env.reset(initial_state, deterministic=True, rng_seed=42)
    event = {
        "event_id": "e1",
        "t_s": 700,
        "agent_id": "SYSTEM",
        "key_id": "ed25519:key_system_control",
        "signature": "GOLDEN_TEST_ACCEPT",
        "action_type": "UPDATE_ROSTER",
        "args": {"roster": {"A_RECEPTION": "ROLE_ANALYTICS", "A_ANALYTICS": "ROLE_RECEPTION"}},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert result["status"] == "ACCEPTED"
    assert result.get("emits") == ["UPDATE_ROSTER"]
    control = result.get("control_decision")
    assert control is not None
    assert control.get("allowed") is True
    assert control.get("reason_code") is None
    assert control.get("role_id") == R_SYSTEM_CONTROL_ROLE
    assert control.get("signature_passed") is True


def test_control_decision_in_log_entry() -> None:
    """control_decision is included in episode log entry when present in step result."""
    from labtrust_gym.logging.episode_log import build_log_entry

    event = {
        "event_id": "e1",
        "t_s": 700,
        "agent_id": "SYSTEM",
        "action_type": "UPDATE_ROSTER",
        "args": {},
    }
    result = {
        "status": "BLOCKED",
        "emits": [],
        "blocked_reason_code": "SIG_MISSING",
        "hashchain": {"head_hash": "h", "length": 0, "last_event_hash": ""},
        "control_decision": {
            "allowed": False,
            "reason_code": "SIG_MISSING",
            "role_id": "R_SYSTEM_CONTROL",
            "signature_passed": False,
        },
    }
    entry = build_log_entry(event, result)
    assert "control_decision" in entry
    assert entry["control_decision"]["allowed"] is False
    assert entry["control_decision"]["reason_code"] == "SIG_MISSING"
