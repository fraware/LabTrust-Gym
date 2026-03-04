"""
Tests for artifact_safety: encryption at rest, integrity, key rotation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.security.artifact_safety import (
    read_artifact_safe,
    should_encrypt_artifacts,
    verify_artifact_integrity,
    write_artifact_safe,
    write_artifact_with_integrity,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_write_read_plaintext_when_no_key(tmp_path: Path) -> None:
    """Without LABTRUST_ARTIFACT_ENCRYPTION_KEY, data is written and read as plaintext."""
    env_prev = os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY", None)
    os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY_LEGACY", None)
    try:
        assert should_encrypt_artifacts() is False
        p = tmp_path / "plain.txt"
        write_artifact_safe(p, b"hello", sensitive=True)
        assert p.read_bytes() == b"hello"
        assert read_artifact_safe(p) == b"hello"
        write_artifact_safe(p, "utf8 text", sensitive=True)
        assert read_artifact_safe(p) == b"utf8 text"
    finally:
        if env_prev is not None:
            os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = env_prev


def test_encrypt_decrypt_when_key_set(tmp_path: Path) -> None:
    """With valid Fernet key set, sensitive data is encrypted on write and decrypted on read."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")
    key = Fernet.generate_key()
    env_prev = os.environ.get("LABTRUST_ARTIFACT_ENCRYPTION_KEY")
    os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = key.decode("ascii")
    os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY_LEGACY", None)
    try:
        assert should_encrypt_artifacts() is True
        p = tmp_path / "enc.bin"
        write_artifact_safe(p, b"secret", sensitive=True)
        raw = p.read_bytes()
        assert raw.startswith(b"LABTRUST\1")
        assert raw != b"secret"
        assert read_artifact_safe(p) == b"secret"
    finally:
        if env_prev is not None:
            os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = env_prev
        else:
            os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY", None)


def test_public_mode_sensitive_skips_write(tmp_path: Path) -> None:
    """When public_mode and sensitive, write_artifact_safe does not write."""
    p = tmp_path / "skip.txt"
    write_artifact_safe(p, b"secret", public_mode=True, sensitive=True)
    assert not p.exists()


def test_verify_integrity_encrypted(tmp_path: Path) -> None:
    """Encrypted file: verify_artifact_integrity passes when decrypt succeeds."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")
    key = Fernet.generate_key()
    env_prev = os.environ.get("LABTRUST_ARTIFACT_ENCRYPTION_KEY")
    os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = key.decode("ascii")
    try:
        p = tmp_path / "enc.bin"
        write_artifact_safe(p, b"data", sensitive=True)
        ok, err = verify_artifact_integrity(p)
        assert ok is True
        assert err is None
    finally:
        if env_prev is not None:
            os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = env_prev
        else:
            os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY", None)


def test_verify_integrity_plaintext_with_sha256(tmp_path: Path) -> None:
    """Plaintext with .sha256 sidecar: verify passes when digest matches."""
    p = tmp_path / "plain.txt"
    p.write_bytes(b"hello")
    (tmp_path / "plain.txt.sha256").write_text("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824\n")
    ok, err = verify_artifact_integrity(p)
    assert ok is True
    assert err is None


def test_write_artifact_with_integrity_store_digest(tmp_path: Path) -> None:
    """write_artifact_with_integrity(store_digest=True) creates .sha256 for plaintext."""
    os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY", None)
    p = tmp_path / "out.txt"
    write_artifact_with_integrity(p, b"content", store_digest=True)
    assert p.read_bytes() == b"content"
    digest_path = tmp_path / "out.txt.sha256"
    assert digest_path.exists()
    digest = digest_path.read_text(encoding="utf-8").strip()
    import hashlib

    assert digest == hashlib.sha256(b"content").hexdigest()


def test_key_rotation_read_legacy(tmp_path: Path) -> None:
    """With LEGACY set, artifact written with old key can be read (active then legacy)."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        pytest.skip("cryptography not installed")
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    env_prev_a = os.environ.get("LABTRUST_ARTIFACT_ENCRYPTION_KEY")
    env_prev_l = os.environ.get("LABTRUST_ARTIFACT_ENCRYPTION_KEY_LEGACY")
    os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = old_key.decode("ascii")
    os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY_LEGACY", None)
    try:
        p = tmp_path / "old.bin"
        write_artifact_safe(p, b"old_secret", sensitive=True)
        raw = p.read_bytes()
    finally:
        if env_prev_a is not None:
            os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = env_prev_a
        else:
            os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY", None)
    os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = new_key.decode("ascii")
    os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY_LEGACY"] = old_key.decode("ascii")
    try:
        assert read_artifact_safe(p) == b"old_secret"
    finally:
        os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY_LEGACY", None)
        if env_prev_a is not None:
            os.environ["LABTRUST_ARTIFACT_ENCRYPTION_KEY"] = env_prev_a
        else:
            os.environ.pop("LABTRUST_ARTIFACT_ENCRYPTION_KEY", None)
