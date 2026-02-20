"""
Resolve a policy value from in-memory effective_policy or from disk.

Used by core_env.reset() when building initial state: for each policy key,
use effective_policy[key] if present and valid, otherwise load from
policy_root/relative_path if the file exists, otherwise use a default.
This keeps scenario overrides (effective_policy) and file-based policy
in one place.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar, cast

T = TypeVar("T")


def load_policy_or_effective(
    effective_policy: dict[str, Any] | None,
    key: str,
    policy_root: str | Path | None,
    relative_path: str,
    loader: Callable[[Path], T],
    default: T,
    *,
    validate_value: Callable[[Any], bool] | None = None,
) -> T:
    """
    Resolve policy: effective_policy[key] if present and valid, else load from file, else default.

    If effective_policy is not None and effective_policy.get(key) passes validate_value
    (default: isinstance(x, dict)), return it. Otherwise build path = policy_root / relative_path
    (or Path(relative_path) if policy_root is None); if path.exists(), call loader(path)
    and return; on exception return default. If path does not exist, return default.
    """
    if effective_policy is not None:
        val = effective_policy.get(key)
        if validate_value is None:
            valid = isinstance(val, dict)
        else:
            valid = validate_value(val)
        if valid and val is not None:
            return cast(T, val)
    root = Path(policy_root) if policy_root is not None else Path(".")
    path = root / relative_path
    if not path.exists():
        return default
    try:
        return loader(path)
    except Exception:
        return default
