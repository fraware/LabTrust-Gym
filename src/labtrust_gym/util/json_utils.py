"""
Canonical JSON serialization for hashing and determinism.

Single convention: sort_keys=True, separators=(",", ":") for consistent
output across export, transparency, determinism reports, and coordination.
Event serialization for the audit hash chain remains in engine/audit_log.
"""

from __future__ import annotations

import json
from typing import Any


def canonical_json(obj: Any) -> str:
    """
    Return a canonical JSON string for the given object (deterministic hashing).

    Uses sort_keys=True and separators=(",", ":") for stable, compact output.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))
