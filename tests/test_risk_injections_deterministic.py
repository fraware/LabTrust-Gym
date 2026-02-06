"""
Determinism: same seed => same injection sequence (mutate_obs / mutate_actions).
"""

from __future__ import annotations

import hashlib
import json

import pytest

from labtrust_gym.security.risk_injections import (
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
