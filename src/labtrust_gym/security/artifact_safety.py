"""
B008: Artifact storage safety (encryption at rest, integrity, key rotation).

- LABTRUST_ARTIFACT_ENCRYPTION_KEY: base64-encoded Fernet key (32 bytes). When set,
  write_artifact_safe encrypts sensitive data; read_artifact_safe decrypts.
- LABTRUST_ARTIFACT_ENCRYPTION_KEY_LEGACY: optional second key for rotation; read
  tries active then legacy so old artifacts remain readable.
- Integrity: encrypted blobs are authenticated (Fernet); verify_artifact_integrity
  checks decrypt or optional .sha256 sidecar for plaintext.
- Public mode (e.g. package-release --public): sensitive artifacts omitted/redacted
  by callers; encryption still applies when key is set and sensitive=True.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

# Magic header for encrypted artifact files (9 bytes).
_ARTIFACT_ENC_MAGIC = b"LABTRUST\1"
_KEY_ID_ACTIVE = 0
_KEY_ID_LEGACY = 1


def _get_fernet_keys() -> tuple[bytes | None, bytes | None]:
    """Return (active_key_bytes, legacy_key_bytes). Keys are raw for Fernet."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return (None, None)
    active_b64 = os.environ.get("LABTRUST_ARTIFACT_ENCRYPTION_KEY", "").strip()
    legacy_b64 = os.environ.get("LABTRUST_ARTIFACT_ENCRYPTION_KEY_LEGACY", "").strip()
    active: bytes | None = None
    legacy: bytes | None = None
    if active_b64:
        try:
            active = active_b64.encode("ascii")
            Fernet(active)
        except Exception:
            active = None
    if legacy_b64:
        try:
            legacy = legacy_b64.encode("ascii")
            Fernet(legacy)
        except Exception:
            legacy = None
    return (active, legacy)


def should_encrypt_artifacts() -> bool:
    """
    Return True if LABTRUST_ARTIFACT_ENCRYPTION_KEY is set and valid.

    When True, write_artifact_safe encrypts sensitive data; read_artifact_safe
    decrypts. Key must be a base64-encoded Fernet key (e.g. from
    cryptography.fernet.Fernet.generate_key()).
    """
    active, _ = _get_fernet_keys()
    return active is not None


def write_artifact_safe(
    path: Path,
    data: bytes | str,
    *,
    public_mode: bool = False,
    sensitive: bool = True,
) -> None:
    """
    Write artifact to path with optional encryption and safety checks.

    - If public_mode and sensitive: do not write (caller should have redacted).
    - If should_encrypt_artifacts() and sensitive: encrypt with active key and
      write magic + key_id + ciphertext. Parent dirs created.
    - Otherwise: write data as plaintext. Parent dirs created.
    """
    if public_mode and sensitive:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    active, _ = _get_fernet_keys()
    if active is not None and sensitive:
        try:
            from cryptography.fernet import Fernet

            f = Fernet(active)
            token = f.encrypt(data)
            path.write_bytes(_ARTIFACT_ENC_MAGIC + bytes([_KEY_ID_ACTIVE]) + token)
            return
        except Exception:
            pass
    path.write_bytes(data)


def read_artifact_safe(path: Path) -> bytes:
    """
    Read artifact from path. Decrypts if file has encryption magic; otherwise
    returns raw bytes. Tries active key then legacy key for decryption.
    Raises ValueError if file is encrypted but decryption fails (e.g. wrong key).
    """
    path = Path(path)
    raw = path.read_bytes()
    if not raw.startswith(_ARTIFACT_ENC_MAGIC) or len(raw) <= len(_ARTIFACT_ENC_MAGIC) + 1:
        return raw
    token = raw[len(_ARTIFACT_ENC_MAGIC) + 1 :]
    active, legacy = _get_fernet_keys()
    for key in (active, legacy):
        if key is None:
            continue
        try:
            from cryptography.fernet import Fernet

            f = Fernet(key)
            return f.decrypt(token)
        except Exception:
            continue
    raise ValueError("artifact decryption failed (invalid or missing key)")


def verify_artifact_integrity(path: Path) -> tuple[bool, str | None]:
    """
    Verify artifact integrity. Returns (ok, error_message).

    - Encrypted file: integrity is verified by successful decryption (Fernet
      authenticity). Returns (True, None) if decrypt succeeds.
    - Plaintext file: if path.sha256 exists, recompute SHA-256 of path and
      compare; otherwise returns (True, None) (no digest to check).
    """
    path = Path(path)
    if not path.exists():
        return (False, "file not found")
    raw = path.read_bytes()
    if raw.startswith(_ARTIFACT_ENC_MAGIC) and len(raw) > len(_ARTIFACT_ENC_MAGIC) + 1:
        try:
            read_artifact_safe(path)
            return (True, None)
        except Exception as e:
            return (False, f"decrypt/integrity failed: {e}")
    digest_path = path.with_suffix(path.suffix + ".sha256")
    if digest_path.exists():
        try:
            expected = digest_path.read_text(encoding="utf-8").strip().split()
            expected_hex = expected[0] if expected else ""
            actual = hashlib.sha256(raw).hexdigest()
            if actual != expected_hex:
                return (False, f"sha256 mismatch: expected {expected_hex[:16]}...")
            return (True, None)
        except Exception as e:
            return (False, f"digest check failed: {e}")
    return (True, None)


def write_artifact_with_integrity(
    path: Path,
    data: bytes | str,
    *,
    public_mode: bool = False,
    sensitive: bool = True,
    store_digest: bool = False,
) -> None:
    """
    Write artifact and optionally store a .sha256 sidecar for plaintext.

    When store_digest=True and data is written as plaintext, also write
    path.sha256 containing the SHA-256 hex digest. Encrypted writes do not
    need a sidecar (Fernet provides authenticity).
    """
    write_artifact_safe(path, data, public_mode=public_mode, sensitive=sensitive)
    if store_digest and not (public_mode and sensitive):
        path = Path(path)
        raw = path.read_bytes()
        if not raw.startswith(_ARTIFACT_ENC_MAGIC):
            digest = hashlib.sha256(raw).hexdigest()
            path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8")
