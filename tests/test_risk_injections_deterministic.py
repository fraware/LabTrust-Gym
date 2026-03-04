"""
Determinism: same seed => same injection sequence (mutate_obs / mutate_actions).
"""

from __future__ import annotations

import hashlib
import json

import pytest

from labtrust_gym.security.risk_injections import (
    RESERVED_NOOP_INJECTION_IDS,
    is_reserved_injection,
    make_injector,
)


def _sequence_hash(seed: int, injection_id: str, steps: int, intensity: float = 1.0) -> str:
    """Deterministic hash of (obs_audits, action_audits) over steps."""
    inj = make_injector(injection_id, intensity=intensity, seed_offset=0)
    inj.reset(seed, None)
    obs = {
        "worker_0": {"queue_has_head": [0, 1], "zone_id": "Z_A"},
        "worker_1": {"zone_id": "Z_B"},
    }
    actions_dict = {
        "worker_0": {"action_index": 5, "args": {"device_id": "D1"}},
        "worker_1": {"action_index": 5},
        "worker_2": {"action_index": 3},
    }
    seq = []
    for _ in range(steps):
        obs, audit_obs = inj.mutate_obs(obs)
        act, audit_actions = inj.mutate_actions(actions_dict)
        step_rec = {
            "audit_obs": audit_obs is not None,
            "audit_actions_len": len(audit_actions),
            "action_0": act.get("worker_0", {}).get("action_index"),
        }
        if audit_actions:
            step_rec["first_audit_injection_id"] = audit_actions[0].get("injection_id")
            step_rec["first_audit_payload"] = audit_actions[0].get("injection_payload")
        for aid in act:
            if act[aid].get("_spoofed_agent_id") or act[aid].get("key_id"):
                step_rec["spoofed"] = (
                    aid,
                    act[aid].get("_spoofed_agent_id"),
                    act[aid].get("key_id"),
                )
                break
        seq.append(json.dumps(step_rec, sort_keys=True))
    return hashlib.sha256("\n".join(seq).encode()).hexdigest()


@pytest.mark.parametrize(
    "injection_id",
    [
        "INJ-COMMS-POISON-001",
        "INJ-CLOCK-SKEW-001",
        "INJ-ID-SPOOF-001",
        "INJ-DOS-PLANNER-001",
        "INJ-COLLUSION-001",
        "INJ-TOOL-MISPARAM-001",
        "INJ-MEMORY-POISON-001",
        "INJ-LLM-PROMPT-INJECT-COORD-001",
        "INJ-LLM-TOOL-ESCALATION-001",
        "INJ-ID-REPLAY-COORD-001",
        "INJ-COLLUSION-MARKET-001",
        "INJ-MEMORY-POISON-COORD-001",
        "INJ-CONSENSUS-POISON-001",
        "INJ-TIMING-QUEUE-001",
        "INJ-PARTIAL-OBS-001",
        "INJ-BLAME-SHIFT-001",
        "inj_device_fail",
        "inj_msg_poison",
        "inj_collusion_handoff",
    ],
)
def test_same_seed_same_injection_sequence(injection_id: str) -> None:
    """Two runs with same seed produce identical injection sequence hash."""
    steps = 15
    seed = 99
    h1 = _sequence_hash(seed, injection_id, steps)
    h2 = _sequence_hash(seed, injection_id, steps)
    assert h1 == h2


def test_different_seed_different_sequence() -> None:
    """Different seeds -> different sequences for injectors using RNG per step (e.g. ID-SPOOF)."""
    h1 = _sequence_hash(1, "INJ-ID-SPOOF-001", 20)
    h2 = _sequence_hash(2, "INJ-ID-SPOOF-001", 20)
    assert h1 != h2


def test_unknown_injection_raises() -> None:
    """Unknown injection_id raises ValueError."""
    with pytest.raises(ValueError, match="Unknown injection_id"):
        make_injector("INJ-UNKNOWN-999")


@pytest.mark.parametrize("injection_id", list(RESERVED_NOOP_INJECTION_IDS))
def test_reserved_injectors_never_mutate_state(injection_id: str) -> None:
    """Reserved (NoOp) injectors never change obs or actions; downstream cannot confuse with real attacks."""
    inj = make_injector(injection_id, intensity=0.5, seed_offset=0)
    inj.reset(42, None)
    obs = {"worker_0": {"zone_id": "Z_A"}, "worker_1": {"zone_id": "Z_B"}}
    actions_dict = {"worker_0": {"action_index": 3}, "worker_1": {"action_index": 5}}
    for _ in range(5):
        out_obs, audit_obs = inj.mutate_obs(obs)
        out_act, audit_act = inj.mutate_actions(actions_dict)
        assert out_obs == obs, "reserved injector must not mutate obs"
        assert out_act == actions_dict, "reserved injector must not mutate actions"
        inj.observe_step([])


def test_reserved_injectors_emit_reserved_flag() -> None:
    """Reserved injectors emit reserved flag in get_metrics() and in audit payload (telemetry)."""
    inj = make_injector("none", seed_offset=0)  # none is reserved NoOpInjector
    inj.reset(1, None)
    obs = {"worker_0": {"z": 1}}
    actions_dict = {"worker_0": {"action_index": 0}}
    audits_seen = []
    for _ in range(3):
        _, audit_obs = inj.mutate_obs(obs)
        _, audit_actions = inj.mutate_actions(actions_dict)
        if audit_actions:
            audits_seen.extend(audit_actions)
        inj.observe_step([])
    metrics = inj.get_metrics()
    assert metrics.get("reserved") is True, "get_metrics() must include reserved=True for reserved injectors"
    assert any((a.get("injection_payload") or {}).get("reserved") is True for a in audits_seen), (
        "at least one audit entry must have injection_payload.reserved=True"
    )


def test_is_reserved_injection() -> None:
    """is_reserved_injection identifies reserved vs implemented."""
    assert is_reserved_injection("none") is True
    assert is_reserved_injection("inj_untrusted_payload") is True
    assert is_reserved_injection("INJ-ID-SPOOF-001") is False
    assert is_reserved_injection("INJ-COMMS-POISON-001") is False
    assert is_reserved_injection("inj_device_fail") is False
    assert is_reserved_injection("inj_msg_poison") is False
    assert is_reserved_injection("inj_tool_selection_noise") is False
    assert is_reserved_injection("inj_collusion_handoff") is False


def test_inj_device_fail_applies_at_deterministic_step() -> None:
    """inj_device_fail sets _device_fault in obs at a deterministic step."""
    from labtrust_gym.security.risk_injections import DeviceFailInjector, InjectionConfig

    cfg = InjectionConfig(injection_id="inj_device_fail", intensity=1.0, seed_offset=0)
    inj = DeviceFailInjector(cfg)
    inj.reset(seed=100, injection_config=None)
    obs = {"worker_0": {"zone_id": "Z_A"}, "worker_1": {"zone_id": "Z_B"}}
    applied_at = None
    for step in range(15):
        out_obs, audit = inj.mutate_obs(obs)
        if audit is not None:
            applied_at = step
            assert any(out_obs.get(a, {}).get("_device_fault") for a in out_obs if isinstance(out_obs.get(a), dict))
        inj.observe_step([])
    assert applied_at is not None, "device fault must apply at some step"
    inj2 = DeviceFailInjector(cfg)
    inj2.reset(seed=100, injection_config=None)
    applied_at2 = None
    for step in range(15):
        out_obs, audit = inj2.mutate_obs(obs)
        if audit is not None:
            applied_at2 = step
        inj2.observe_step([])
    assert applied_at == applied_at2, "same seed must apply at same step"


def test_inj_msg_poison_corrupts_messages_deterministically() -> None:
    """inj_msg_poison corrupts message payload deterministically."""
    from labtrust_gym.security.risk_injections import InjectionConfig, MsgPoisonInjector

    cfg = InjectionConfig(injection_id="inj_msg_poison", intensity=1.0, seed_offset=0)
    inj = MsgPoisonInjector(cfg)
    inj.reset(seed=7, injection_config=None)
    messages = [{"payload": "hello", "from": "a"}, {"payload": "world", "from": "b"}]
    out, audit = inj.mutate_messages(messages)
    assert out != messages
    assert any("_POISON" in str(m.get("payload", m.get("_poison", ""))) for m in out)
    assert audit is not None
    assert audit.get("injection_id") == "inj_msg_poison"


def test_inj_collusion_handoff_mutates_messages_observable() -> None:
    """inj_collusion_handoff duplicates a message; observable effect and audit."""
    from labtrust_gym.security.risk_injections import CollusionHandoffInjector, InjectionConfig

    cfg = InjectionConfig(injection_id="inj_collusion_handoff", intensity=1.0, seed_offset=0)
    inj = CollusionHandoffInjector(cfg)
    inj.reset(seed=42, injection_config=None)
    messages = [{"handoff": "work_1", "from": "a"}, {"handoff": "work_2", "from": "b"}]
    out, audit = inj.mutate_messages(messages)
    # With intensity 1.0, one message is duplicated (list length +1)
    assert len(out) >= len(messages), "handoff injector must add or preserve messages"
    assert audit is not None
    assert audit.get("injection_id") == "inj_collusion_handoff"
    assert (audit.get("injection_payload") or {}).get("type") == "handoff_duplicate"
    metrics = inj.get_metrics()
    assert metrics.get("first_application_step") is not None or len(out) > len(messages)
