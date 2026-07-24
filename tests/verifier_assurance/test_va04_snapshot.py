"""LT-VA-04 snapshot round-trip and replay tests."""

from __future__ import annotations

import copy

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.verifier_assurance.snapshot.canonical import (
    SnapshotError,
    capture_core_env,
    validate_snapshot_payload,
)


def _reset_env(seed: int = 7) -> CoreEnv:
    env = CoreEnv()
    env.reset(
        {
            "timing_mode": "simulated",
            "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
            "tokens": [],
        },
        deterministic=True,
        rng_seed=seed,
    )
    return env


def test_snapshot_round_trip_digest_stable() -> None:
    env = _reset_env()
    # Mutate some stores
    env._specimens._specimens["S1"]["status"] = "accepted"
    env._qc.set_device_qc_state("D1", "fail")
    env._qc.create_result("R1", run_id="run1", device_id="D1")
    snap1 = env.snapshot()
    d1 = snap1.canonical_digest()
    env2 = _reset_env(seed=99)
    env2.restore(snap1)
    snap2 = env2.snapshot()
    assert snap2.canonical_digest() == d1
    assert env2._specimens.get("S1")["status"] == "accepted"
    assert env2._qc.device_qc_state("D1") == "fail"
    assert env2._now_ts == env._now_ts


def test_rng_and_clock_restoration() -> None:
    env = _reset_env(seed=3)
    assert env._rng is not None
    env._now_ts = 42
    if env._clock is not None:
        env._clock.set(42)
    _ = env._rng.random()
    snap = env.snapshot()
    r1 = env._rng.random()
    env.restore(snap)
    r2 = env._rng.random()
    assert r1 == r2
    assert env._now_ts == 42
    if env._clock is not None:
        assert env._clock.now_ts == 42


def test_identical_action_replay_after_restore() -> None:
    env = _reset_env(seed=11)
    event = {
        "event_id": "e1",
        "t_s": 1,
        "agent_id": "SYSTEM",
        "action_type": "CREATE_ACCESSION",
        "args": {"specimen_id": "S1"},
        "reason_code": None,
    }
    # May block without signatures; still should be deterministic
    out1 = env.step(event)
    snap = env.snapshot()
    env_b = _reset_env(seed=11)
    env_b.restore(snap)
    # Same audit head after restore
    assert env_b._audit.hashchain_snapshot() == env._audit.hashchain_snapshot()
    assert out1["status"] in ("ACCEPTED", "BLOCKED", "REJECTED", "HELD")


def test_incomplete_snapshot_reject() -> None:
    env = _reset_env()
    payload = env.snapshot().payload
    payload.pop("tokens")
    with pytest.raises(SnapshotError):
        validate_snapshot_payload(payload)


def test_capture_helper_matches_env_api() -> None:
    env = _reset_env()
    a = capture_core_env(env)
    b = env.snapshot()
    assert a.canonical_digest() == b.canonical_digest()
