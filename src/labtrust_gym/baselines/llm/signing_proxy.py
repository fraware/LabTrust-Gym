"""
Signing proxy for LLM agents: key selection and event payload signing.

- select_key(agent_id, role_id, now_ts_s, key_registry) -> key_id: choose first ACTIVE
  key bound to agent_id/role_id valid at now_ts_s; revoked/expired keys are not selected.
- sign_event_payload(...): build canonical payload and Ed25519-sign; return base64 signature.
- Agent never receives private key; proxy holds key material and attaches signature.
- Tests: use fixture private keys under tests/fixtures/keys/.
- Live runs: generate_ephemeral_keypair() and run-local key registry overlay (do not modify repo policy).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from labtrust_gym.engine.signatures import (
    build_signing_payload,
    canonical_payload_bytes,
)


def _key_valid_at(key: Dict[str, Any], now_ts: int) -> Tuple[bool, Optional[str]]:
    """Return (True, None) if key is valid at now_ts; else (False, reason_code)."""
    status = (key.get("status") or "ACTIVE").strip().upper()
    if status == "REVOKED":
        return False, "SIG_KEY_REVOKED"
    if status == "EXPIRED":
        return False, "SIG_KEY_EXPIRED"
    not_before = key.get("not_before_ts_s")
    if not_before is not None and now_ts < int(not_before):
        return False, "SIG_KEY_NOT_YET_VALID"
    not_after = key.get("not_after_ts_s")
    if not_after is not None and now_ts > int(not_after):
        return False, "SIG_KEY_EXPIRED"
    return True, None


def select_key(
    agent_id: str,
    role_id: str,
    now_ts_s: int,
    key_registry: Dict[str, Any],
) -> Optional[str]:
    """
    Select first ACTIVE key in registry bound to agent_id and role_id, valid at now_ts_s.

    Revoked and expired keys are not selected. Returns key_id or None if no valid key.
    """
    agent_id = (agent_id or "").strip()
    role_id = (role_id or "").strip()
    for k in key_registry.get("keys", []):
        if not isinstance(k, dict):
            continue
        if (k.get("agent_id") or "").strip() != agent_id:
            continue
        if (k.get("role_id") or "").strip() != role_id:
            continue
        valid, _ = _key_valid_at(k, now_ts_s)
        if valid:
            kid = k.get("key_id")
            if kid:
                return str(kid)
    return None


def sign_event_payload(
    action: Dict[str, Any],
    event_id: str,
    t_s: int,
    agent_id: str,
    prev_hash: str,
    partner_id: Optional[str],
    policy_fingerprint: Optional[str],
    private_key: bytes,
) -> Optional[str]:
    """
    Build canonical signing payload from action and sign with Ed25519 private key.

    action: dict with action_type, args, token_refs (same shape as event).
    private_key: 32-byte Ed25519 private key (seed).
    Returns base64-encoded signature or None on failure.
    """
    if len(private_key) != 32:
        return None
    action_type = (action.get("action_type") or "NOOP").strip()
    action_params = dict(action.get("args") or {})
    token_refs = list(action.get("token_refs") or [])
    payload = build_signing_payload(
        event_id=event_id,
        t_s=t_s,
        agent_id=(agent_id or "").strip(),
        action_type=action_type,
        action_params=action_params,
        token_refs=token_refs,
        partner_id=partner_id,
        policy_fingerprint=policy_fingerprint,
        prev_hash=prev_hash or "",
    )
    payload_bytes = canonical_payload_bytes(payload)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        key = Ed25519PrivateKey.from_private_bytes(private_key)
        sig_raw = key.sign(payload_bytes)
    except Exception:
        return None
    return base64.b64encode(sig_raw).decode("ascii")


def load_private_key_from_fixture(path: Path) -> Optional[bytes]:
    """
    Load 32-byte Ed25519 private key from fixture file (base64 or raw).

    path: .b64 (base64) or raw 32-byte file. Returns None on failure.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        key_bytes = base64.b64decode(text, validate=True)
    except Exception:
        key_bytes = raw
    if len(key_bytes) != 32:
        return None
    return key_bytes


def generate_ephemeral_keypair() -> Tuple[bytes, str]:
    """
    Generate a new Ed25519 keypair for run-local signing.

    Returns (private_key_32_bytes, public_key_base64).
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    key = Ed25519PrivateKey.generate()
    priv = key.private_bytes_raw()
    pub_b64 = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    return priv, pub_b64


def ensure_run_ephemeral_key(
    run_dir: Path,
    agent_id: str,
    role_id: str,
    key_registry_base: Dict[str, Any],
    key_id_prefix: str = "ed25519:run_",
) -> Tuple[Dict[str, Any], Callable[[str], Optional[bytes]]]:
    """
    Ensure an ephemeral key exists for this run; write overlay to run_dir and merge with base.

    Does not modify repo policy. Returns (merged_key_registry, get_private_key).
    get_private_key(key_id) returns 32-byte private key for the run key, or None.
    """
    key_id = f"{key_id_prefix}{agent_id}_{role_id}".replace(":", "_")
    overlay_path = run_dir / "key_registry_overlay.v0.1.yaml"
    private_path = run_dir / "run_private_key.b64"
    if private_path.exists() and overlay_path.exists():
        try:
            priv_b64 = private_path.read_text(encoding="utf-8").strip()
            priv = base64.b64decode(priv_b64, validate=True)
            if len(priv) != 32:
                priv = None
        except Exception:
            priv = None
        if priv is not None:
            from labtrust_gym.policy.loader import load_yaml

            overlay = load_yaml(overlay_path)
            kr = (overlay.get("key_registry") or {}).get("keys") or []
            keys = list(key_registry_base.get("keys") or []) + list(kr)
            merged = {
                "version": key_registry_base.get("version", "0.1"),
                "keys": keys,
            }

            def get_private_key(kid: str) -> Optional[bytes]:
                if kid == key_id:
                    return priv
                return None

            return merged, get_private_key
    priv_bytes, pub_b64 = generate_ephemeral_keypair()
    run_dir.mkdir(parents=True, exist_ok=True)
    private_path.write_text(
        base64.b64encode(priv_bytes).decode("ascii"), encoding="utf-8"
    )
    entry = {
        "key_id": key_id,
        "public_key": pub_b64,
        "agent_id": agent_id,
        "role_id": role_id,
        "status": "ACTIVE",
        "not_before_ts_s": None,
        "not_after_ts_s": None,
        "rotation_of_key_id": None,
    }
    overlay = {
        "key_registry": {
            "version": "0.1",
            "keys": [entry],
        }
    }
    try:
        import yaml

        overlay_path.write_text(
            yaml.dump(overlay, default_flow_style=False), encoding="utf-8"
        )
    except Exception:
        overlay_path.write_text(
            f'key_registry:\n  version: "0.1"\n  keys:\n  - key_id: "{key_id}"\n'
            f'    public_key: "{pub_b64}"\n    agent_id: "{agent_id}"\n'
            f'    role_id: "{role_id}"\n    status: ACTIVE\n',
            encoding="utf-8",
        )
    keys_base = list(key_registry_base.get("keys") or [])
    merged = {
        "version": key_registry_base.get("version", "0.1"),
        "keys": keys_base + [entry],
    }

    def get_private_key(kid: str) -> Optional[bytes]:
        if kid == key_id:
            return priv_bytes
        return None

    return merged, get_private_key
