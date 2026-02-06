"""
Policy-driven enforcement: throttle_agent, kill_switch, freeze_zone, forensic_freeze.

Tests:
- Throttle on violation
- Escalation on repeated violations
- Deterministic enforcement ordering
"""

from pathlib import Path

import pytest

from labtrust_gym.engine.enforcement import (
    EnforcementEngine,
    apply_enforcement,
    load_enforcement_map,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_load_enforcement_map() -> None:
    """Load enforcement map returns version and rules."""
    root = _repo_root()
    path = root / "policy/enforcement/enforcement_map.v0.1.yaml"
    if not path.exists():
        pytest.skip("enforcement_map.v0.1.yaml not found")
    data = load_enforcement_map(path)
    assert "version" in data
    assert "rules" in data
    assert isinstance(data["rules"], list)
    if data["rules"]:
        rule = data["rules"][0]
        assert "rule_id" in rule
        assert "match" in rule
        assert "action" in rule
        assert rule["action"]["type"] in (
            "throttle_agent",
            "kill_switch",
            "freeze_zone",
            "forensic_freeze",
        )


def test_enforcement_throttle_on_violation() -> None:
    """First violation matching a rule produces throttle_agent enforcement."""
    root = _repo_root()
    path = root / "policy/enforcement/enforcement_map.v0.1.yaml"
    if not path.exists():
        pytest.skip("enforcement_map.v0.1.yaml not found")
    engine = EnforcementEngine(path)
    event = {"event_id": "e1", "agent_id": "A1", "action_type": "ACK_CRITICAL_RESULT"}
    violations = [
        {"invariant_id": "INV-CRIT-004", "status": "VIOLATION", "reason_code": "CRIT_NO_READBACK"},
    ]
    enforcements = engine.apply(event, violations, audit_callback=None)
    assert len(enforcements) >= 1
    throttle = [e for e in enforcements if e.get("type") == "throttle_agent"]
    assert len(throttle) >= 1
    assert throttle[0].get("target") == "A1"
    assert throttle[0].get("duration_s") is not None
    assert throttle[0].get("reason_code") == "CRIT_NO_READBACK"


def test_enforcement_escalation_on_repeated_violations() -> None:
    """Repeated violations for same rule escalate (e.g. throttle -> freeze_zone)."""
    root = _repo_root()
    path = root / "policy/enforcement/enforcement_map.v0.1.yaml"
    if not path.exists():
        pytest.skip("enforcement_map.v0.1.yaml not found")
    engine = EnforcementEngine(path)
    event = {"event_id": "e1", "agent_id": "A1"}
    # INV-ZONE-005: first violation -> throttle, second -> freeze_zone
    violations_zone = [
        {
            "invariant_id": "INV-ZONE-005",
            "status": "VIOLATION",
            "reason_code": "RC_DOOR_OPEN_TOO_LONG",
        },
    ]
    e1 = engine.apply(event, violations_zone, audit_callback=None)
    assert len(e1) >= 1
    first_types = [x.get("type") for x in e1]
    assert "throttle_agent" in first_types
    # Same rule again: escalation tier 2 (violation_count_min 2)
    e2 = engine.apply(event, violations_zone, audit_callback=None)
    assert len(e2) >= 1
    [x.get("type") for x in e2]
    # Should have freeze_zone on second occurrence (escalation)
    freeze = [x for x in e2 if x.get("type") == "freeze_zone"]
    assert len(freeze) >= 1
    assert freeze[0].get("zone_id") == "Z_RESTRICTED_BIOHAZARD"


def test_enforcement_deterministic_ordering() -> None:
    """Same event and violations produce same enforcements in same order."""
    root = _repo_root()
    path = root / "policy/enforcement/enforcement_map.v0.1.yaml"
    if not path.exists():
        pytest.skip("enforcement_map.v0.1.yaml not found")
    event = {"event_id": "e1", "agent_id": "A1"}
    violations = [
        {"invariant_id": "INV-CRIT-004", "status": "VIOLATION"},
        {"invariant_id": "INV-ZONE-005", "status": "VIOLATION"},
    ]
    engine1 = EnforcementEngine(path)
    engine2 = EnforcementEngine(path)
    e1 = engine1.apply(event, violations, audit_callback=None)
    e2 = engine2.apply(event, violations, audit_callback=None)
    assert len(e1) == len(e2)
    for a, b in zip(e1, e2):
        assert a.get("type") == b.get("type")
        assert a.get("rule_id") == b.get("rule_id")


def test_apply_enforcement_without_engine_returns_empty() -> None:
    """apply_enforcement with engine=None returns []."""
    event = {"event_id": "e1", "agent_id": "A1"}
    violations = [{"invariant_id": "INV-CRIT-004", "status": "VIOLATION"}]
    result = apply_enforcement(event, violations, engine=None)
    assert result == []


def test_enforcement_reset_counts() -> None:
    """reset_counts clears violation counts; next violation is treated as first."""
    root = _repo_root()
    path = root / "policy/enforcement/enforcement_map.v0.1.yaml"
    if not path.exists():
        pytest.skip("enforcement_map.v0.1.yaml not found")
    engine = EnforcementEngine(path)
    event = {"event_id": "e1", "agent_id": "A1"}
    violations = [{"invariant_id": "INV-ZONE-005", "status": "VIOLATION"}]
    engine.apply(event, violations, audit_callback=None)
    engine.apply(event, violations, audit_callback=None)
    engine.reset_counts()
    e = engine.apply(event, violations, audit_callback=None)
    # After reset, first violation again -> throttle (not freeze_zone)
    throttle = [x for x in e if x.get("type") == "throttle_agent"]
    assert len(throttle) >= 1


def test_core_env_enforcements_when_disabled() -> None:
    """Golden suite / default: enforcement_enabled false => enforcements always []."""
    from labtrust_gym.engine.core_env import CoreEnv

    env = CoreEnv()
    initial = {
        "system": {"now_s": 0, "downtime_active": False},
        "agents": [{"agent_id": "A1", "zone_id": "Z_SRA_RECEPTION"}],
        "specimens": [],
        "tokens": [],
    }
    env.reset(initial, deterministic=True, rng_seed=42)
    event = {
        "event_id": "e1",
        "t_s": 100,
        "agent_id": "A1",
        "action_type": "TICK",
        "args": {},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert "enforcements" in result
    assert result["enforcements"] == []
