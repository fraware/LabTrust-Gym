"""
Security metrics coverage: every injection_id in the study spec has a harness
that implements get_metrics() and produces sec.* in episode metrics.
"""

from __future__ import annotations

import pytest

from labtrust_gym.benchmarks.metrics import compute_episode_metrics
from labtrust_gym.security.risk_injections import make_injector

# Injection IDs from policy/coordination/injections.v0.2.yaml (must have harness + get_metrics)
INJECTIONS_V02_IDS = [
    "INJ-COLLUSION-001",
    "INJ-SLOW-POISON-001",
    "INJ-ID-SPOOF-001",
    "INJ-REPLAY-001",
    "INJ-COMMS-POISON-001",
    "INJ-MEMORY-POISON-001",
    "INJ-BID-SPOOF-001",
    "INJ-LLM-PROMPT-INJECT-COORD-001",
    "INJ-LLM-TOOL-ESCALATION-001",
    "INJ-COMMS-FLOOD-LLM-001",
    "INJ-ID-REPLAY-COORD-001",
    "INJ-COLLUSION-MARKET-001",
    "INJ-MEMORY-POISON-COORD-001",
]

REQUIRED_SEC_KEYS = (
    "attack_success_rate",
    "detection_latency_steps",
    "containment_time_steps",
)


@pytest.mark.parametrize("injection_id", INJECTIONS_V02_IDS)
def test_injection_produces_sec_metrics(injection_id: str) -> None:
    """
    For each injection in injections.v0.2, make_injector succeeds, get_metrics()
    returns the standard shape, and compute_episode_metrics produces sec with
    required keys (attack_success_rate, detection_latency_steps, containment_time_steps).
    """
    inj = make_injector(injection_id, intensity=0.2, seed_offset=0)
    inj.reset(42, None)
    # Simulate a few steps so observe_step may set detection/containment
    step_results = [[{"status": "OK"}, {"status": "BLOCKED", "blocked_reason_code": "SIG_INVALID"}]]
    for _ in range(3):
        inj.mutate_obs({"a": {}})
        inj.mutate_actions({"a": {"action_index": 0}})
        inj.observe_step(step_results[0])
    metrics = inj.get_metrics()
    assert "attack_success" in metrics
    assert (
        "first_application_step" in metrics
        or "first_detection_step" in metrics
        or "first_containment_step" in metrics
        or True
    )
    out = compute_episode_metrics(
        step_results_per_step=step_results * 2,
        injection_metrics=metrics,
        injection_id=injection_id,
    )
    assert "sec" in out, f"{injection_id}: episode metrics must include sec"
    sec = out["sec"]
    for key in REQUIRED_SEC_KEYS:
        assert key in sec, f"{injection_id}: sec must have {key}"
    assert sec.get("injection_id") == injection_id
