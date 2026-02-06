"""
Spoof injection must be blocked when strict_signatures=True; attack_success_rate=0.
"""

from __future__ import annotations

from labtrust_gym.security.risk_injections import IdSpoofInjector, InjectionConfig


def test_spoof_injection_produces_audit_entry() -> None:
    """INJ-ID-SPOOF-001 mutate_actions returns audit entry and spoofed key_id in action."""
    config = InjectionConfig(
        injection_id="INJ-ID-SPOOF-001",
        intensity=1.0,
        seed_offset=0,
    )
    inj = IdSpoofInjector(config)
    inj.reset(42, None)
    actions_dict = {
        "worker_0": {
            "action_index": 5,
            "action_type": "START_RUN",
            "args": {"device_id": "D1", "work_id": "W1"},
        },
        "worker_1": {"action_index": 0},
    }
    out, audit_list = inj.mutate_actions(actions_dict)
    assert len(audit_list) >= 1
    assert any(
        a.get("injection_id") == "INJ-ID-SPOOF-001" and "SECURITY_INJECTION_APPLIED" in (a.get("emits") or [])
        for a in audit_list
    )
    spoofed_agent = None
    for aid, ad in out.items():
        if ad.get("_spoofed_agent_id") or ad.get("key_id"):
            spoofed_agent = aid
            break
    assert spoofed_agent is not None


def test_spoof_blocked_reason_codes_in_observe_step() -> None:
    """observe_step records first_detection_step when step_outputs contain blocked with SIG_*."""
    config = InjectionConfig(
        injection_id="INJ-ID-SPOOF-001",
        intensity=1.0,
        seed_offset=0,
    )
    inj = IdSpoofInjector(config)
    inj.reset(42, None)
    inj._applied_this_step = True
    step_outputs = [
        {"status": "BLOCKED", "blocked_reason_code": "SIG_ROLE_MISMATCH", "emits": []},
    ]
    extra = inj.observe_step(step_outputs)
    assert inj._first_detection_step is not None
    assert any("SECURITY_INJECTION_DETECTED" in (e.get("emits") or []) for e in extra)
    assert inj._attack_success is False


def test_spoof_success_only_when_mutating_emit_accepted() -> None:
    """attack_success is True only when applied and a mutating emit (e.g. START_RUN) was not blocked."""
    config = InjectionConfig(
        injection_id="INJ-ID-SPOOF-001",
        intensity=1.0,
        seed_offset=0,
    )
    inj = IdSpoofInjector(config)
    inj.reset(42, None)
    inj._applied_this_step = True
    step_outputs = [
        {"status": "OK", "emits": ["START_RUN"], "blocked_reason_code": None},
    ]
    inj.observe_step(step_outputs)
    assert inj._attack_success is True
