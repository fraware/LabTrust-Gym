"""
B008: Artifact storage safety (encryption stub and public mode).

- LABTRUST_ARTIFACT_ENCRYPTION_KEY: when set, encryption-at-rest is intended;
  current implementation does not encrypt (stub). Artifacts are written as-is.
- Public mode (e.g. package-release --public, ui-export --public) is handled
  by disclosure redaction; sensitive artifacts are omitted or redacted there.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def should_encrypt_artifacts() -> bool:
    """
    Return True if LABTRUST_ARTIFACT_ENCRYPTION_KEY is set.

    When True, callers may choose to skip writing sensitive artifacts to disk
    in plaintext in high-security deployments. Encryption-at-rest is not
    implemented in this stub; the flag allows future implementation or
    integration with an external encryptor.
    """
    key = os.environ.get("LABTRUST_ARTIFACT_ENCRYPTION_KEY", "").strip()
    return bool(key)


def write_artifact_safe(
    path: Path,
    data: bytes | str,
    *,
    public_mode: bool = False,
    sensitive: bool = True,
) -> None:
    """
    Write artifact to path with optional safety checks.

    - If public_mode and sensitive: do not write (caller should have redacted).
    - If should_encrypt_artifacts(): currently writes plaintext; encryption
      is not implemented (stub). Documented in deployment_hardening.md.
    - Otherwise: write data to path. Parent dirs are created.
    """
    if public_mode and sensitive:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def read_artifact_safe(path: Path) -> bytes:
    """Read artifact from path. No decryption (stub)."""
    return Path(path).read_bytes()
