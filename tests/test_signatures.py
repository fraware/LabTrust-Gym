"""
Unit tests for signed actions: canonical payload, key registry, Ed25519 verification.

- Valid signature passes; invalid fails; revoked/expired key fails deterministically.
- Golden GS-SIG-026 (no signature => BLOCKED SIG_MISSING) and GS-SIG-027 (invalid sig => BLOCKED SIG_INVALID)
  are run by test_golden_suite when LABTRUST_RUN_GOLDEN=1.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from labtrust_gym.engine.signatures import (
    build_signing_payload,
    canonical_payload_bytes,
    is_mutating_action,
    load_key_registry,
    verify_action_signature,
    verify_signature,
    SIG_MISSING,
    SIG_INVALID,
    SIG_KEY_REVOKED,
    SIG_KEY_EXPIRED,
)
from labtrust_gym.engine.audit_log import canonical_serialize


def test_build_signing_payload_deterministic() -> None:
    payload = build_signing_payload(
        event_id="e1",
        t_s=100,
        agent_id="A_RECEPTION",
        action_type="MOVE",
        action_params={"from_zone": "Z_A", "to_zone": "Z_B"},
        token_refs=[],
        partner_id=None,
        policy_fingerprint=None,
        prev_hash="abc",
    )
    assert payload["event_id"] == "e1"
    assert payload["t_s"] == 100
    assert payload["action_type"] == "MOVE"
    assert payload["prev_hash"] == "abc"
    bytes1 = canonical_payload_bytes(payload)
    bytes2 = canonical_payload_bytes(payload)
    assert bytes1 == bytes2


def test_canonical_payload_same_as_audit_serialize() -> None:
    """Canonical payload uses same serialization as audit log."""
    payload = build_signing_payload("e1", 0, "A1", "MOVE", {}, [], None, None, "")
    bytes_sig = canonical_payload_bytes(payload)
    bytes_audit = canonical_serialize(payload)
    assert bytes_sig == bytes_audit


def test_load_key_registry() -> None:
    path = Path("policy/keys/key_registry.v0.1.yaml")
    if not path.exists():
        pytest.skip("policy/keys/key_registry.v0.1.yaml not found")
    reg = load_key_registry(path)
    assert "version" in reg
    assert "keys" in reg
    assert isinstance(reg["keys"], list)
    key_ids = [k.get("key_id") for k in reg["keys"] if isinstance(k, dict)]
    assert "ed25519:key_reception" in key_ids


def test_verify_signature_invalid_fails() -> None:
    """Invalid signature (wrong bytes) must fail verification."""
    path = Path("policy/keys/key_registry.v0.1.yaml")
    if not path.exists():
        pytest.skip("policy/keys/key_registry.v0.1.yaml not found")
    reg = load_key_registry(path)
    key = next((k for k in reg["keys"] if k.get("key_id") == "ed25519:key_reception"), None)
    assert key is not None
    pub_b64 = key["public_key"]
    payload_bytes = b"canonical payload"
    wrong_sig_b64 = base64.b64encode(bytes(64)).decode()  # 64 zero bytes
    assert verify_signature(payload_bytes, wrong_sig_b64, pub_b64) is False


def test_verify_signature_valid_passes() -> None:
    """Valid Ed25519 signature over payload must pass."""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        pytest.skip("cryptography not installed")
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_b64 = base64.b64encode(pub.public_bytes_raw()).decode()
    payload_bytes = b"canonical payload"
    sig = priv.sign(payload_bytes)
    sig_b64 = base64.b64encode(sig).decode()
    assert verify_signature(payload_bytes, sig_b64, pub_b64) is True


def test_verify_action_signature_missing() -> None:
    """Event without key_id/signature => (False, SIG_MISSING, info)."""
    event = {"event_id": "e1", "t_s": 0, "agent_id": "A_RECEPTION", "action_type": "MOVE", "args": {}}
    registry = {"version": "0.1", "keys": []}
    passed, reason, info = verify_action_signature(event, "prev", None, None, registry, 0)
    assert passed is False
    assert reason == SIG_MISSING
    assert info and info.get("reason_code") == SIG_MISSING


def test_verify_action_signature_invalid_sig_fails() -> None:
    """Event with key_id + wrong signature => (False, SIG_INVALID, info)."""
    path = Path("policy/keys/key_registry.v0.1.yaml")
    if not path.exists():
        pytest.skip("policy/keys/key_registry.v0.1.yaml not found")
    reg = load_key_registry(path)
    event = {
        "event_id": "e1",
        "t_s": 9010,
        "agent_id": "A_RECEPTION",
        "action_type": "MOVE",
        "args": {"entity_type": "Agent", "entity_id": "A_RECEPTION", "from_zone": "Z_SRA_RECEPTION", "to_zone": "Z_ACCESSIONING"},
        "key_id": "ed25519:key_reception",
        "signature": base64.b64encode(bytes(64)).decode(),
    }
    passed, reason, info = verify_action_signature(event, "prev_hash_here", None, None, reg, 9010)
    assert passed is False
    assert reason == SIG_INVALID
    assert info and info.get("reason_code") == SIG_INVALID


def test_revoked_key_fails() -> None:
    """Key with status REVOKED => (False, SIG_KEY_REVOKED)."""
    reg = {"version": "0.1", "keys": [{"key_id": "k1", "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=", "agent_id": "A_RECEPTION", "role_id": "ROLE_RECEPTION", "status": "REVOKED"}]}
    event = {"event_id": "e1", "t_s": 0, "agent_id": "A_RECEPTION", "action_type": "MOVE", "args": {}, "key_id": "k1", "signature": base64.b64encode(bytes(64)).decode()}
    passed, reason, _ = verify_action_signature(event, "prev", None, None, reg, 0)
    assert passed is False
    assert reason == SIG_KEY_REVOKED


def test_expired_key_fails() -> None:
    """Key with not_after_ts_s < now_ts => (False, SIG_KEY_EXPIRED)."""
    reg = {"version": "0.1", "keys": [{"key_id": "k1", "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=", "agent_id": "A_RECEPTION", "role_id": "ROLE_RECEPTION", "status": "ACTIVE", "not_after_ts_s": 100}]}
    event = {"event_id": "e1", "t_s": 0, "agent_id": "A_RECEPTION", "action_type": "MOVE", "args": {}, "key_id": "k1", "signature": base64.b64encode(bytes(64)).decode()}
    passed, reason, _ = verify_action_signature(event, "prev", None, None, reg, 200)
    assert passed is False
    assert reason == SIG_KEY_EXPIRED


def test_is_mutating_action() -> None:
    assert is_mutating_action("MOVE") is True
    assert is_mutating_action("ACCEPT_SPECIMEN") is True
    assert is_mutating_action("TICK") is True
    assert is_mutating_action("") is False
    assert is_mutating_action("QUERY") is False


def test_gs_sig_026_no_signature_blocked(monkeypatch) -> None:
    """GS-SIG-026: strict mode, mutating action without signature => BLOCKED SIG_MISSING."""
    monkeypatch.setenv("LABTRUST_STRICT_SIGNATURES", "1")
    from labtrust_gym.engine.core_env import CoreEnv
    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [],
        "tokens": [],
        "strict_signatures": True,
    }
    env.reset(initial_state, deterministic=True, rng_seed=12345)
    event = {
        "event_id": "e1",
        "t_s": 9000,
        "agent_id": "A_RECEPTION",
        "action_type": "MOVE",
        "args": {"entity_type": "Agent", "entity_id": "A_RECEPTION", "from_zone": "Z_SRA_RECEPTION", "to_zone": "Z_ACCESSIONING"},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert result["status"] == "BLOCKED"
    assert result["blocked_reason_code"] == "SIG_MISSING"


def test_gs_sig_027_invalid_signature_blocked(monkeypatch) -> None:
    """GS-SIG-027: strict mode, invalid signature => BLOCKED SIG_INVALID."""
    monkeypatch.setenv("LABTRUST_STRICT_SIGNATURES", "1")
    from labtrust_gym.engine.core_env import CoreEnv
    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [],
        "tokens": [],
        "strict_signatures": True,
    }
    env.reset(initial_state, deterministic=True, rng_seed=12345)
    event = {
        "event_id": "e1",
        "t_s": 9010,
        "agent_id": "A_RECEPTION",
        "key_id": "ed25519:key_reception",
        "signature": base64.b64encode(bytes(64)).decode(),
        "action_type": "MOVE",
        "args": {"entity_type": "Agent", "entity_id": "A_RECEPTION", "from_zone": "Z_SRA_RECEPTION", "to_zone": "Z_ACCESSIONING"},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert result["status"] == "BLOCKED"
    assert result["blocked_reason_code"] == "SIG_INVALID"


def test_default_strict_off_mutating_without_sig_accepted() -> None:
    """Without strict_signatures, mutating action without signature is accepted (backward compat)."""
    from labtrust_gym.engine.core_env import CoreEnv
    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [],
        "tokens": [],
        "agents": [{"agent_id": "A_RECEPTION", "zone_id": "Z_SRA_RECEPTION"}],
    }
    env.reset(initial_state, deterministic=True, rng_seed=12345)
    event = {
        "event_id": "e1",
        "t_s": 9000,
        "agent_id": "A_RECEPTION",
        "action_type": "MOVE",
        "args": {"entity_type": "Agent", "entity_id": "A_RECEPTION", "from_zone": "Z_SRA_RECEPTION", "to_zone": "Z_ACCESSIONING"},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert result["status"] == "ACCEPTED"
