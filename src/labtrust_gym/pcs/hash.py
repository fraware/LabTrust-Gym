"""Deterministic hashing for PCS traces and artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(obj: Any) -> str:
    """Serialize *obj* to canonical JSON (sorted keys, compact separators)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_object(obj: Any) -> str:
    return sha256_hex(canonical_json(obj))


def pcs_digest(doc: dict[str, Any]) -> str:
    """PCS-core canonical digest (sha256:...)."""
    try:
        from pcs_core.hash import canonical_hash

        return canonical_hash(doc)
    except ImportError:
        payload = {k: v for k, v in doc.items() if k != "signature_or_digest"}
        sorted_payload = json.loads(canonical_json(payload))
        return f"sha256:{sha256_hex(canonical_json(sorted_payload))}"


def file_digest(path: Path) -> str:
    return f"sha256:{sha256_hex(path.read_bytes())}"


GENESIS_EVENT_HASH = "0" * 64
