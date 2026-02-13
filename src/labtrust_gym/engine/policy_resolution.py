"""
Resolve policy from effective_policy dict or from policy file path.

Used by core_env.reset() to unify "use effective_policy[key] if present,
else load from policy_root/relative_path if exists, else default".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypeVar

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
            return val  # type: ignore[return-value]
    root = Path(policy_root) if policy_root is not None else Path(".")
    path = root / relative_path
    if not path.exists():
        return default
    try:
        return loader(path)
    except Exception:
        return default
