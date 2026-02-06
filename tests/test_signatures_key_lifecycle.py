"""
Key lifecycle: valid key passes; revoked/expired/not-yet-valid blocked with correct reason codes.
"""

import base64
from unittest.mock import patch

from labtrust_gym.engine.signatures import (
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


# 64-byte placeholder for signature (valid base64 length for Ed25519)
PLACEHOLDER_SIG_B64 = base64.b64encode(b"x" * 64).decode()


def test_valid_key_passes() -> None:
    """ACTIVE key, in time window, agent_id match -> verification can pass (valid signature)."""
    registry = _registry_with_keys(
        [
            {
                "key_id": "ed25519:key_test",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
                "status": "ACTIVE",
                "not_before_ts_s": None,
                "not_after_ts_s": None,
            },
        ]
    )
    event = _minimal_event("ed25519:key_test", PLACEHOLDER_SIG_B64, "A_RECEPTION")
    with patch("labtrust_gym.engine.signatures.verify_signature", return_value=True):
        passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is True
    assert reason is None
    assert info is not None and info.get("passed") is True
    assert info.get("reason_code") is None


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
    event = _minimal_event("ed25519:key_revoked", PLACEHOLDER_SIG_B64, "A_INSIDER_0")
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
    event = _minimal_event("ed25519:key_expired", PLACEHOLDER_SIG_B64, "A_RECEPTION")
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
    event = _minimal_event("ed25519:key_future", PLACEHOLDER_SIG_B64, "A_RECEPTION")
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
    event = _minimal_event("ed25519:key_status_expired", PLACEHOLDER_SIG_B64, "A_RECEPTION")
    passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is False
    assert reason == SIG_KEY_EXPIRED
    assert info is not None and info.get("reason_code") == SIG_KEY_EXPIRED


def test_missing_status_defaults_active() -> None:
    """Key without status field defaults to ACTIVE (backward compat)."""
    registry = _registry_with_keys(
        [
            {
                "key_id": "ed25519:key_no_status",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
            },
        ]
    )
    event = _minimal_event("ed25519:key_no_status", PLACEHOLDER_SIG_B64, "A_RECEPTION")
    with patch("labtrust_gym.engine.signatures.verify_signature", return_value=True):
        passed, reason, info = verify_action_signature(event, "prev_hash_0", None, None, registry, now_ts=500)
    assert passed is True
    assert reason is None
