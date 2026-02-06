"""
Resolve repo root and policy root for dev (repo) vs installed (package data).

- get_repo_root(): path P such that P / "policy" contains policy files (emits/, schemas/, ...).
  Used by loader/validate and runner. When installed from wheel, P is the package policy parent.
- Policy can be: (1) LABTRUST_POLICY_DIR env (path to policy dir), (2) package data labtrust_gym/policy, (3) repo policy/.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_repo_root() -> Path:
    """Walk up from cwd to find a directory containing policy/."""
    cwd = Path.cwd()
    for p in [cwd, cwd.parent]:
        if (p / "policy").is_dir() and (p / "policy" / "emits").exists():
            return p
    return cwd


def get_repo_root() -> Path:
    """
    Return path P such that P / "policy" is the policy directory.
    Order: LABTRUST_POLICY_DIR (policy dir -> P = parent), package data, repo.
    """
    env_policy = os.environ.get("LABTRUST_POLICY_DIR")
    if env_policy:
        p = Path(env_policy).resolve()
        if p.is_dir():
            return p.parent
    try:
        from importlib.resources import files

        pkg_policy = files("labtrust_gym") / "policy"
        pkg_path = Path(str(pkg_policy))
        if pkg_path.is_dir() and (pkg_path / "emits").exists():
            return pkg_path.parent
    except Exception:
        pass
    repo = _find_repo_root()
    if (repo / "policy").is_dir():
        return repo
    return repo
