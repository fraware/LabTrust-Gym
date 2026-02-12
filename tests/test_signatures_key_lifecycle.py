"""
Key lifecycle: valid key passes; revoked/expired/not-yet-valid blocked with correct reason codes.
Real Ed25519 signatures in-test; tampering fails verification.
"""

import base64

from labtrust_gym.engine.signatures import (
    build_signing_payload,
    canonical_payload_bytes,
    sign_payload_bytes,
    SIG_KEY_EXPIRED,
    SIG_KEY_NOT_YET_VALID,
    SIG_KEY_REVOKED,
    verify_action_signature,
)


def _minimal_event(key_id: str, signature_b64: str, agent_id: str = "A_RECEPTION") -> dict:
    return {
        "event_id": "e1",
        "t_s": 500,
        "agent_id": agent_id,
        "action_type": "MOVE",
        "args": {
            "entity_type": "Agent",
            "entity_id": agent_id,
            "from_zone": "Z_A",
            "to_zone": "Z_B",
        },
        "token_refs": [],
        "key_id": key_id,
        "signature": signature_b64,
    }


def _registry_with_keys(keys: list) -> dict:
    return {"version": "0.1", "keys": keys}


# 64-byte invalid signature (valid base64 length for Ed25519) for lifecycle tests that fail before crypto
_DUMMY_SIG_B64 = base64.b64encode(b"\x00" * 64).decode()


def _generate_keypair_and_sign_event(event: dict, prev_hash: str) -> tuple[dict, str]:
    """Generate Ed25519 keypair, sign event payload, return (registry_with_public_key, signature_b64)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")
    priv_raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    payload = build_signing_payload(
        event_id=event["event_id"],
        t_s=event["t_s"],
        agent_id=event["agent_id"],
        action_type=event["action_type"],
        action_params=event.get("args") or {},
        token_refs=event.get("token_refs") or [],
        partner_id=None,
        policy_fingerprint=None,
        prev_hash=prev_hash,
    )
    payload_bytes = canonical_payload_bytes(payload)
    sig_b64 = sign_payload_bytes(payload_bytes, priv_raw)
    assert sig_b64 is not None
    key_id = event.get("key_id") or "ed25519:key_test"
    registry = _registry_with_keys(
        [
            {
                "key_id": key_id,
                "public_key": pub_b64,
                "agent_id": event.get("agent_id", "A_RECEPTION"),
                "role_id": "ROLE_RECEPTION",
                "status": "ACTIVE",
                "not_before_ts_s": None,
                "not_after_ts_s": None,
            },
        ]
    )
    return registry, sig_b64


def test_valid_key_passes() -> None:
    """ACTIVE key, in time window, agent_id match -> verification passes with real signature."""
    event = _minimal_event("ed25519:key_test", "", "A_RECEPTION")
    registry, sig_b64 = _generate_keypair_and_sign_event(event, "prev_hash_0")
    event["signature"] = sig_b64
    passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is True
    assert reason is None
    assert info is not None and info.get("passed") is True
    assert info.get("reason_code") is None


def test_tampering_fails_verification() -> None:
    """Tampering with event payload causes signature verification to fail."""
    event = _minimal_event("ed25519:key_tamper", "", "A_RECEPTION")
    registry, sig_b64 = _generate_keypair_and_sign_event(event, "prev_hash_0")
    event["signature"] = sig_b64
    passed, _, _ = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is True
    event["args"]["to_zone"] = "Z_TAMPERED"
    passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is False
    assert info is not None and info.get("reason_code") == "SIG_INVALID"


def test_revoked_key_blocked() -> None:
    """Key with status REVOKED -> BLOCKED with SIG_KEY_REVOKED."""
    registry = _registry_with_keys(
        [
            {
                "key_id": "ed25519:key_revoked",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_INSIDER_0",
                "role_id": "ROLE_INSIDER",
                "status": "REVOKED",
                "not_before_ts_s": None,
                "not_after_ts_s": None,
            },
        ]
    )
    event = _minimal_event("ed25519:key_revoked", _DUMMY_SIG_B64, "A_INSIDER_0")
    passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is False
    assert reason == SIG_KEY_REVOKED
    assert info is not None and info.get("reason_code") == SIG_KEY_REVOKED


def test_expired_window_blocked() -> None:
    """Key with not_after_ts_s in the past -> BLOCKED with SIG_KEY_EXPIRED."""
    registry = _registry_with_keys(
        [
            {
                "key_id": "ed25519:key_expired",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
                "status": "ACTIVE",
                "not_before_ts_s": None,
                "not_after_ts_s": 100,
            },
        ]
    )
    event = _minimal_event("ed25519:key_expired", _DUMMY_SIG_B64, "A_RECEPTION")
    passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=200)
    assert passed is False
    assert reason == SIG_KEY_EXPIRED
    assert info is not None and info.get("reason_code") == SIG_KEY_EXPIRED


def test_not_before_window_blocked() -> None:
    """Key with not_before_ts_s in the future -> BLOCKED with SIG_KEY_NOT_YET_VALID."""
    registry = _registry_with_keys(
        [
            {
                "key_id": "ed25519:key_future",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
                "status": "ACTIVE",
                "not_before_ts_s": 1000,
                "not_after_ts_s": None,
            },
        ]
    )
    event = _minimal_event("ed25519:key_future", _DUMMY_SIG_B64, "A_RECEPTION")
    passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=100)
    assert passed is False
    assert reason == SIG_KEY_NOT_YET_VALID
    assert info is not None and info.get("reason_code") == SIG_KEY_NOT_YET_VALID


def test_status_expired_blocked() -> None:
    """Key with status EXPIRED -> BLOCKED with SIG_KEY_EXPIRED."""
    registry = _registry_with_keys(
        [
            {
                "key_id": "ed25519:key_status_expired",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
                "status": "EXPIRED",
                "not_before_ts_s": None,
                "not_after_ts_s": None,
            },
        ]
    )
    event = _minimal_event("ed25519:key_status_expired", _DUMMY_SIG_B64, "A_RECEPTION")
    passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is False
    assert reason == SIG_KEY_EXPIRED
    assert info is not None and info.get("reason_code") == SIG_KEY_EXPIRED


def test_missing_status_defaults_active() -> None:
    """Key without status field defaults to ACTIVE (backward compat); real signature."""
    event = _minimal_event("ed25519:key_no_status", "", "A_RECEPTION")
    registry, sig_b64 = _generate_keypair_and_sign_event(event, "prev_hash_0")
    registry["keys"][0].pop("status", None)
    event["signature"] = sig_b64
    passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is True
    assert reason is None
