"""
R-TOOL-002 (Tool execution failure): DeviceFailInjector and containment.

DeviceFailInjector (inj_device_fail) injects _device_fault into observation
at a deterministic step. This test evidences that the injection is applied,
auditable, and that step outputs indicating fault handling can be observed.
"""

from __future__ import annotations

import pytest

from labtrust_gym.security.risk_injections import (
    EMIT_INJECTION_APPLIED,
    DeviceFailInjector,
    InjectionConfig,
)


def test_device_fail_injector_applies_at_fault_step() -> None:
    """DeviceFailInjector applies at deterministic fault_step and emits audit."""
    # seed=0, seed_offset=0 -> fault_step = (0+0)%10+1 = 1
    config = InjectionConfig(
        injection_id="inj_device_fail",
        intensity=1.0,
        seed_offset=0,
    )
    inj = DeviceFailInjector(config)
    inj.reset(0, None)
    assert inj._fault_step == 1

    obs = {"agent_0": {"my_zone_idx": 0}, "agent_1": {"my_zone_idx": 1}}
    mutated, audit = inj.mutate_obs(obs)
    assert audit is None, "Step 0: no application yet"
    inj._step = 1
    mutated, audit = inj._mutate_obs_impl(obs)
    assert audit is not None
    assert EMIT_INJECTION_APPLIED in (audit.get("emits") or [])
    assert audit.get("injection_id") == "inj_device_fail"
    assert "fault_step" in (audit.get("injection_payload") or {})
    for k, v in mutated.items():
        if isinstance(v, dict) and v.get("_device_fault"):
            break
    else:
        pytest.fail("No _device_fault in mutated obs")


def test_device_fail_observe_step_containment() -> None:
    """When step_output has BLOCKED (e.g. device fault), containment is recorded."""
    config = InjectionConfig(
        injection_id="inj_device_fail",
        intensity=1.0,
        seed_offset=0,
    )
    inj = DeviceFailInjector(config)
    inj.reset(0, None)
    inj._applied_this_step = True
    step_outputs = [
        {
            "status": "BLOCKED",
            "blocked_reason_code": "RC_DEVICE_FAULT",
            "emits": [],
        },
    ]
    inj.observe_step(step_outputs)
    assert inj._first_containment_step is not None
    assert inj._attack_success is False
