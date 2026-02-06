"""
B008: Filesystem boundaries for deployment.

- LABTRUST_RUNS_DIR: configurable base directory for run/artifact output.
- Path traversal: reject filename parameters that escape the base dir.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_runs_dir() -> Path:
    """
    Return the base directory for run/artifact output.

    Uses LABTRUST_RUNS_DIR if set (must be absolute or resolved against cwd).
    Otherwise returns current working directory so CLI behavior is unchanged.
    """
    env = os.environ.get("LABTRUST_RUNS_DIR", "").strip()
    if env:
        p = Path(env)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()
    return Path.cwd()


def resolve_within_base(base_dir: Path, requested: str) -> Path | None:
    """
    Resolve requested path relative to base_dir; return None if it escapes.

    Disallows path traversal (..), absolute paths, and symlinks that escape.
    requested should be a single path component or relative path (e.g. "run_1" or "run_1/logs").
    """
    base = base_dir.resolve()
    try:
        combined = (base / requested).resolve()
    except (OSError, RuntimeError):
        return None
    try:
        combined.relative_to(base)
    except ValueError:
        return None
    if ".." in requested or requested.startswith("/") or (len(requested) >= 2 and requested[1] == ":"):
        return None
    return combined


def is_safe_filename_component(name: str) -> bool:
    """
    Return True if name is safe as a single path component (no traversal, no absolute).
    """
    if not name or name in (".", ".."):
        return False
    if "/" in name or "\\" in name or "\0" in name:
        return False
    if len(name) >= 2 and name[1] == ":":
        return False
    return True


def assert_under_runs_dir(path: Path) -> None:
    """
    Raise ValueError if path is not under get_runs_dir().

    Use when the server or a service writes files so that all output stays under LABTRUST_RUNS_DIR.
    """
    runs = get_runs_dir().resolve()
    try:
        path.resolve().relative_to(runs)
    except ValueError:
        raise ValueError(f"Path {path} is not under LABTRUST_RUNS_DIR {runs}") from None
