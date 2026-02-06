"""
Load and validate reason codes from policy/reason_codes/reason_code_registry.

- Load registry: codes list with code, namespace, severity, description, etc.
- Validate that a code exists in the registry (for strict mode).
- Lookup: get(code) returns code info dict or None.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml


def load_reason_code_registry(path: str | Path) -> dict[str, dict[str, Any]]:
    """
    Load reason code registry from YAML.     Returns dict code -> code info (namespace, severity, description, etc.).
    Path may be relative to cwd or absolute.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        raise
    reg = data.get("reason_code_registry")
    if reg is None:
        raise PolicyLoadError(p, "missing top-level key 'reason_code_registry'")
    codes_list = reg.get("codes")
    if codes_list is None:
        raise PolicyLoadError(p, "reason_code_registry.codes missing")
    if not isinstance(codes_list, list):
        raise PolicyLoadError(
            p,
            f"reason_code_registry.codes must be a list, got {type(codes_list).__name__}",
        )
    out: dict[str, dict[str, Any]] = {}
    for entry in codes_list:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code")
        if code and isinstance(code, str):
            out[code] = dict(entry)
    return out


def get_code(registry: dict[str, dict[str, Any]], code: str) -> dict[str, Any] | None:
    """Lookup code in registry. Returns code info dict or None if not found."""
    return registry.get(code) if code else None


def allowed_codes(registry: dict[str, dict[str, Any]]) -> set[str]:
    """Return set of all registered code strings."""
    return set(registry.keys())


def validate_reason_code(
    code: str | None,
    registry: dict[str, dict[str, Any]],
    *,
    event_id: str = "",
    context: str = "reason_code",
) -> None:
    """
    If code is not None and not in registry, raise AssertionError.
    Used when LABTRUST_STRICT_REASON_CODES=1 to enforce that blocked_reason_code
    and action reason_code (when present) are in the registry.
    """
    if code is None:
        return
    if code not in registry:
        msg = f"[{event_id}] unknown {context} {code!r} | registered={sorted(registry.keys())}"
        raise AssertionError(msg)
