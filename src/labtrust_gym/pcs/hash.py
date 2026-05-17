"""PCS artifact hashing via pcs-core canonical hash SDK."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

GENESIS_EVENT_HASH = "0" * 64


def _require_pcs_core_hash():
    try:
        from pcs_core.hash import (
            canonical_hash,
            canonical_json_bytes,
            canonicalize_for_hash,
        )
    except ImportError as exc:
        raise RuntimeError(
            "pcs-core is required for PCS canonical hashing "
            "(pip install -e /path/to/pcs-core/python)"
        ) from exc
    return canonical_hash, canonical_json_bytes, canonicalize_for_hash


def canonical_json(obj: dict[str, Any]) -> str:
    """Canonical JSON string for PCS artifact hashing (pcs-core algorithm)."""
    _, canonical_json_bytes, _ = _require_pcs_core_hash()
    if not isinstance(obj, dict):
        raise TypeError("canonical_json expects a dict for PCS artifact hashing")
    return canonical_json_bytes(obj).decode("utf-8")


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_object(obj: dict[str, Any]) -> str:
    """Return bare hex digest (no sha256: prefix) of canonical PCS JSON."""
    digest = pcs_digest(obj)
    return digest.removeprefix("sha256:")


def pcs_digest(doc: dict[str, Any]) -> str:
    """PCS-core canonical digest (sha256:...), ignoring signature_or_digest."""
    canonical_hash, _, _ = _require_pcs_core_hash()
    return canonical_hash(doc)


def pcs_digest_ignoring_signature(doc: dict[str, Any]) -> str:
    """Explicit alias for vector tests (signature field excluded by pcs-core)."""
    return pcs_digest(doc)


def file_digest(path: Path) -> str:
    """Raw file content digest (not canonical JSON)."""
    return f"sha256:{sha256_hex(path.read_bytes())}"


def hash_vector_dir(artifact_type: str) -> Path:
    """Path to pcs-core frozen hash vector directory."""
    from pcs_core.paths import hash_vectors_dir

    return hash_vectors_dir() / artifact_type
