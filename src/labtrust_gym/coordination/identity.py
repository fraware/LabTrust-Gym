"""
Signed agent identity for coordination messages: deterministic key material per agent,
sign_message and verify_message for authentic, attributable coordination traffic.

Used by the coordination bus for verify-on-receive; keys are derived from a master
seed in simulation for reproducibility.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

# Reason codes (must match policy/reason_codes/reason_code_registry.v0.1.yaml)
COORD_SIGNATURE_INVALID = "COORD_SIGNATURE_INVALID"
COORD_REPLAY_DETECTED = "COORD_REPLAY_DETECTED"
COORD_SENDER_NOT_AUTHORIZED = "COORD_SENDER_NOT_AUTHORIZED"

# Envelope keys
KEY_SENDER_ID = "sender_id"
KEY_NONCE = "nonce"
KEY_EPOCH = "epoch"
KEY_MESSAGE_TYPE = "message_type"
KEY_PAYLOAD = "payload"
KEY_PAYLOAD_HASH = "payload_hash"
KEY_SIGNATURE = "signature"


def _derive_key_seed(master_seed: int, agent_id: str) -> bytes:
    """Deterministic 32-byte seed for Ed25519 from master_seed and agent_id."""
    msg = f"{master_seed}\0{agent_id}".encode()
    return hashlib.sha256(msg).digest()[:32]


def build_key_store(agent_ids: list[str], master_seed: int) -> dict[str, tuple[Any, str]]:
    """
    Build key store for sign/verify. Returns dict agent_id -> (private_key, public_key_b64).
    Deterministic: same agent_ids and master_seed yield same keys.
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        return {}

    store: dict[str, tuple[Any, str]] = {}
    for aid in agent_ids:
        seed = _derive_key_seed(master_seed, aid)
        try:
            private_key = Ed25519PrivateKey.from_private_bytes(seed)
        except Exception:
            continue
        public_key = private_key.public_key()
        pub_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        store[aid] = (private_key, base64.b64encode(pub_bytes).decode("ascii"))
    return store


def _canonical_payload(envelope_without_sig: dict[str, Any]) -> bytes:
    """Canonical bytes for signing (deterministic JSON)."""
    return json.dumps(envelope_without_sig, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_message(
    message_type: str,
    payload: dict[str, Any],
    sender_id: str,
    nonce: int,
    epoch: int,
    key_store: dict[str, tuple[Any, str]],
) -> dict[str, Any] | None:
    """
    Produce a signed coordination message envelope. Returns None if sender has no key.
    Envelope: sender_id, nonce, epoch, message_type, payload, payload_hash, signature (base64).
    """
    if sender_id not in key_store:
        return None
    private_key, _ = key_store[sender_id]
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:32]
    envelope = {
        KEY_SENDER_ID: sender_id,
        KEY_NONCE: nonce,
        KEY_EPOCH: epoch,
        KEY_MESSAGE_TYPE: message_type,
        KEY_PAYLOAD: payload,
        KEY_PAYLOAD_HASH: payload_hash,
    }
    to_sign = _canonical_payload(envelope)
    try:
        sig = private_key.sign(to_sign)
        envelope[KEY_SIGNATURE] = base64.b64encode(sig).decode("ascii")
    except Exception:
        return None
    return envelope


def verify_message(
    envelope: dict[str, Any],
    key_store: dict[str, tuple[Any, str]],
) -> tuple[bool, str | None, str | None]:
    """
    Verify signature on a coordination message envelope.
    Returns (ok, sender_id, reason_code). If ok then reason_code is None.
    On failure: ok=False, sender_id from envelope (untrusted), reason_code = COORD_SIGNATURE_INVALID.
    """
    sender_id = envelope.get(KEY_SENDER_ID)
    if not isinstance(sender_id, str) or not sender_id.strip():
        return False, None, COORD_SIGNATURE_INVALID
    if sender_id not in key_store:
        return False, str(sender_id), COORD_SIGNATURE_INVALID
    _, pub_b64 = key_store[sender_id]
    sig_b64 = envelope.get(KEY_SIGNATURE)
    if not sig_b64:
        return False, sender_id, COORD_SIGNATURE_INVALID
    envelope_without_sig = {k: v for k, v in envelope.items() if k != KEY_SIGNATURE}
    payload_bytes = _canonical_payload(envelope_without_sig)
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False, sender_id, COORD_SIGNATURE_INVALID
    try:
        sig_raw = base64.b64decode(sig_b64, validate=True)
        pub_raw = base64.b64decode(pub_b64, validate=True)
    except Exception:
        return False, sender_id, COORD_SIGNATURE_INVALID
    if len(sig_raw) != 64 or len(pub_raw) != 32:
        return False, sender_id, COORD_SIGNATURE_INVALID
    try:
        pub_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        pub_key.verify(sig_raw, payload_bytes)
        return True, sender_id, None
    except InvalidSignature:
        return False, sender_id, COORD_SIGNATURE_INVALID
    except Exception:
        return False, sender_id, COORD_SIGNATURE_INVALID


def verify_message_find_signer(
    envelope: dict[str, Any],
    key_store: dict[str, tuple[Any, str]],
) -> tuple[bool, str | None]:
    """
    Try verifying with each key in key_store. Returns (ok, actual_sender_id).
    Used to detect spoof: envelope claims sender_id A but signature verifies
    with key B -> actual_sender_id is B.
    """
    sig_b64 = envelope.get(KEY_SIGNATURE)
    if not sig_b64:
        return False, None
    envelope_without_sig = {k: v for k, v in envelope.items() if k != KEY_SIGNATURE}
    payload_bytes = _canonical_payload(envelope_without_sig)
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False, None
    try:
        sig_raw = base64.b64decode(sig_b64, validate=True)
    except Exception:
        return False, None
    if len(sig_raw) != 64:
        return False, None
    for aid, (_, pub_b64) in key_store.items():
        try:
            pub_raw = base64.b64decode(pub_b64, validate=True)
        except Exception:
            continue
        if len(pub_raw) != 32:
            continue
        try:
            pub_key = Ed25519PublicKey.from_public_bytes(pub_raw)
            pub_key.verify(sig_raw, payload_bytes)
            return True, aid
        except (InvalidSignature, Exception):
            continue
    return False, None
