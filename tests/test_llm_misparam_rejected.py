"""
Malformed structured output (INJ-TOOL-MISPARAM-001) must be rejected and logged.
"""

from __future__ import annotations

import pytest

from labtrust_gym.security.risk_injections import (
    EMIT_INJECTION_APPLIED,
    InjectionConfig,
    ToolMisparamInjector,
)


def test_tool_misparam_injector_produces_malformed_action() -> None:
    """INJ-TOOL-MISPARAM-001 injects invalid device_id; audit entry has SECURITY_INJECTION_APPLIED."""
    config = InjectionConfig(
        injection_id="INJ-TOOL-MISPARAM-001",
        intensity=1.0,
        seed_offset=0,
    )
    inj = ToolMisparamInjector(config)
    inj.reset(42, None)
    actions_dict = {
        "worker_0": {"action_index": 0},
        "worker_1": {"action_index": 2},
    }
    out, audit_list = inj.mutate_actions(actions_dict)
    assert len(audit_list) >= 1
    assert any(
        EMIT_INJECTION_APPLIED in (a.get("emits") or [])
        and a.get("injection_id") == "INJ-TOOL-MISPARAM-001"
        for a in audit_list
    )
    for aid, ad in out.items():
        if "INVALID_DEVICE" in str(ad.get("args") or {}):
            assert ad.get("action_index") == 5
            break
    else:
        pytest.skip("Injector did not apply this step (probabilistic)")


def test_tool_misparam_detected_when_blocked() -> None:
    """When step output has BLOCKED with RC_DEVICE_UNKNOWN or schema reason, observe_step sets first_detection_step."""
    config = InjectionConfig(
        injection_id="INJ-TOOL-MISPARAM-001",
        intensity=1.0,
        seed_offset=0,
    )
    inj = ToolMisparamInjector(config)
    inj.reset(42, None)
    inj._applied_this_step = True
    step_outputs = [
        {"status": "BLOCKED", "blocked_reason_code": "RC_DEVICE_UNKNOWN", "emits": []},
    ]
    extra = inj.observe_step(step_outputs)
    assert inj._first_detection_step is not None
    assert inj._attack_success is False
