"""
Tests for signed agent identity and replay-safe coordination bus.

- Forged sender signature rejected deterministically.
- Replay rejected deterministically.
- Sender not authorized when policy restricts allowed_senders.
- Violations/emits logged as step-result fragments without breaking runner output contract.
"""

from __future__ import annotations

import pytest

from labtrust_gym.coordination.bus import SignedMessageBus
from labtrust_gym.coordination.identity import (
    COORD_REPLAY_DETECTED,
    COORD_SENDER_NOT_AUTHORIZED,
    COORD_SIGNATURE_INVALID,
    build_key_store,
    sign_message,
    verify_message,
)


def test_build_key_store_deterministic() -> None:
    """Same agent_ids and master_seed yield same keys."""
    agents = ["A_OPS_0", "A_RUNNER_0"]
    store1 = build_key_store(agents, master_seed=42)
    store2 = build_key_store(agents, master_seed=42)
    assert len(store1) == 2
    assert set(store1) == set(store2)
    for aid in agents:
        _, pub1 = store1[aid]
        _, pub2 = store2[aid]
        assert pub1 == pub2


def test_sign_verify_roundtrip() -> None:
    """Valid signed message verifies."""
    agents = ["A_OPS_0"]
    store = build_key_store(agents, master_seed=1)
    if not store:
        pytest.skip("cryptography not available")
    env = sign_message(
        message_type="BID",
        payload={"value": 10},
        sender_id="A_OPS_0",
        nonce=1,
        epoch=0,
        key_store=store,
    )
    assert env is not None
    ok, sender, reason = verify_message(env, store)
    assert ok is True
    assert sender == "A_OPS_0"
    assert reason is None


def test_forged_sender_signature_rejected() -> None:
    """Tampering sender_id or payload breaks signature; verify returns COORD_SIGNATURE_INVALID."""
    agents = ["A_OPS_0", "A_RUNNER_0"]
    store = build_key_store(agents, master_seed=2)
    if not store:
        pytest.skip("cryptography not available")
    env = sign_message(
        message_type="BID",
        payload={"value": 10},
        sender_id="A_OPS_0",
        nonce=1,
        epoch=0,
        key_store=store,
    )
    assert env is not None
    # Forge: claim to be A_RUNNER_0
    forged = dict(env)
    forged["sender_id"] = "A_RUNNER_0"
    ok, _, reason = verify_message(forged, store)
    assert ok is False
    assert reason == COORD_SIGNATURE_INVALID

    # Forge: tamper payload; signature was over original envelope so verification fails
    forged2 = dict(env)
    forged2["payload"] = {"value": 99}
    ok2, _, reason2 = verify_message(forged2, store)
    assert ok2 is False
    assert reason2 == COORD_SIGNATURE_INVALID


def test_replay_rejected_deterministically() -> None:
    """Same envelope submitted twice to bus: first accepted, second COORD_REPLAY_DETECTED."""
    agents = ["A_OPS_0"]
    store = build_key_store(agents, master_seed=3)
    if not store:
        pytest.skip("cryptography not available")
    policy = {"allowed_message_types": ["BID"], "allowed_senders": None}
    bus = SignedMessageBus(key_store=store, identity_policy=policy)
    env = sign_message(
        message_type="BID",
        payload={"value": 5},
        sender_id="A_OPS_0",
        nonce=100,
        epoch=0,
        key_store=store,
    )
    assert env is not None
    accepted1, delivered1, violation1 = bus.receive(env)
    assert accepted1 is True
    assert delivered1 is not None
    assert violation1 is None

    accepted2, delivered2, violation2 = bus.receive(env)
    assert accepted2 is False
    assert delivered2 is None
    assert violation2 is not None
    assert violation2.get("emits") == [COORD_REPLAY_DETECTED]
    assert any(v.get("reason_code") == COORD_REPLAY_DETECTED for v in violation2.get("violations") or [])


def test_replay_of_old_epoch_rejected() -> None:
    """Message signed with old epoch is rejected when bus current epoch is different (epoch binding)."""
    agents = ["A_OPS_0"]
    store = build_key_store(agents, master_seed=4)
    if not store:
        pytest.skip("cryptography not available")
    policy = {"allowed_message_types": ["BID"], "allowed_senders": None}
    current_epoch = [1]

    def epoch_fn():
        return current_epoch[0]

    bus = SignedMessageBus(key_store=store, identity_policy=policy, epoch_fn=epoch_fn)
    env = sign_message(
        message_type="BID",
        payload={"value": 7},
        sender_id="A_OPS_0",
        nonce=200,
        epoch=0,
        key_store=store,
    )
    assert env is not None
    accepted, delivered, violation = bus.receive(env)
    assert accepted is False
    assert delivered is None
    assert violation is not None
    assert violation.get("emits") == [COORD_SENDER_NOT_AUTHORIZED]
    assert any(v.get("reason_code") == COORD_SENDER_NOT_AUTHORIZED for v in violation.get("violations") or [])


def test_sender_not_authorized() -> None:
    """When allowed_senders is set, sender not in list gets COORD_SENDER_NOT_AUTHORIZED."""
    agents = ["A_OPS_0", "A_RUNNER_0"]
    store = build_key_store(agents, master_seed=4)
    if not store:
        pytest.skip("cryptography not available")
    policy = {
        "allowed_message_types": ["BID"],
        "allowed_senders": ["A_OPS_0"],
    }
    bus = SignedMessageBus(key_store=store, identity_policy=policy)
    env = sign_message(
        message_type="BID",
        payload={"value": 1},
        sender_id="A_RUNNER_0",
        nonce=1,
        epoch=0,
        key_store=store,
    )
    assert env is not None
    accepted, delivered, violation = bus.receive(env)
    assert accepted is False
    assert violation is not None
    assert violation.get("emits") == [COORD_SENDER_NOT_AUTHORIZED]
    assert any(v.get("reason_code") == COORD_SENDER_NOT_AUTHORIZED for v in violation.get("violations") or [])


def test_violation_step_result_runner_contract() -> None:
    """Violation fragments have violations + emits; compute_episode_metrics accepts them."""
    from labtrust_gym.benchmarks.metrics import compute_episode_metrics

    agents = ["A_OPS_0"]
    store = build_key_store(agents, master_seed=5)
    if not store:
        pytest.skip("cryptography not available")
    policy = {"allowed_message_types": ["BID"], "allowed_senders": None}
    bus = SignedMessageBus(key_store=store, identity_policy=policy)
    # Produce a replay violation
    env = sign_message(
        message_type="BID",
        payload={},
        sender_id="A_OPS_0",
        nonce=1,
        epoch=0,
        key_store=store,
    )
    assert env is not None
    bus.receive(env)
    _, _, violation = bus.receive(env)
    assert violation is not None
    assert "violations" in violation
    assert "emits" in violation
    # Step results: one normal step, one step with coord violation fragment
    step_results_per_step = [
        [{"emits": [], "violations": []}],
        [violation],
    ]
    metrics = compute_episode_metrics(step_results_per_step)
    assert "violations_by_invariant_id" in metrics
    assert COORD_REPLAY_DETECTED in metrics["violations_by_invariant_id"]
    assert metrics["violations_by_invariant_id"][COORD_REPLAY_DETECTED] == 1
