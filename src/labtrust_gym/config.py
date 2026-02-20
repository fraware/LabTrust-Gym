"""
Resolve repository root and policy directory paths.

Used in both development (repo) and installed (package data) setups.
get_repo_root() returns a path P such that P / "policy" contains the policy
files (emits/, schemas/, etc.); the loader, validator, and runner use it.
Policy location: (1) LABTRUST_POLICY_DIR env, (2) package data labtrust_gym/policy,
(3) repo policy/. policy_path(policy_root, *parts) builds paths under the
policy directory from the repo root and segment names.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from labtrust_gym.errors import PolicyPathError


def get_policy_dir(policy_root: Path) -> Path:
    """Return the policy directory (policy_root / "policy")."""
    return policy_root / "policy"


def policy_path(policy_root: Path, *parts: str) -> Path:
    """
    Build a path under the policy directory. policy_root is the repo root (such that
    policy_root / "policy" is the policy dir). parts are relative path segments
    under policy (e.g. "golden", "security_attack_suite.v0.1.yaml").
    """
    return policy_root / "policy" / Path(*parts)


def _find_repo_root() -> Path:
    """Walk up from cwd to find a directory containing policy/."""
    cwd = Path.cwd()
    for p in [cwd, cwd.parent]:
        if (p / "policy").is_dir() and (p / "policy" / "emits").exists():
            return p
    return cwd


def get_effective_path(
    policy_root: Path,
    profile: dict[str, Any] | None,
    field: str,
    default_relative: str,
) -> Path:
    """
    Resolve a path from the lab profile. If profile has a non-null value for field,
    interpret it as relative to policy_root (or absolute if it looks absolute);
    otherwise return policy_root / "policy" / default_relative.
    """
    base = policy_root / "policy"
    if profile and profile.get(field) not in (None, ""):
        raw = profile[field]
        if isinstance(raw, str):
            p = Path(raw)
            if p.is_absolute():
                return p
            return (policy_root / raw).resolve()
    return base / default_relative


def load_lab_profile(policy_root: Path, profile_id: str) -> dict | None:
    """
    Load a lab profile from policy/lab_profiles/<profile_id>.v0.1.yaml.
    Returns the profile dict or None if not found/invalid.
    When policy/lab_profiles/lab_profile.v0.1.schema.json exists and jsonschema
    is available, the loaded YAML is validated; on validation failure returns None.
    """
    path = policy_path(policy_root, "lab_profiles", f"{profile_id}.v0.1.yaml")
    if not path.exists():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        schema_path = policy_path(policy_root, "lab_profiles", "lab_profile.v0.1.schema.json")
        if schema_path.exists():
            try:
                import json
                import jsonschema
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                jsonschema.validate(data, schema)
            except Exception:
                return None
        return data
    except Exception:
        return None


def get_repo_root() -> Path:
    """
    Return path P such that P / "policy" is the policy directory.
    Order: LABTRUST_POLICY_DIR (policy dir -> P = parent), package data, repo.
    Raises PolicyPathError when LABTRUST_POLICY_DIR is set but invalid, or when
    no policy directory is found (e.g. cwd is not inside a repo with policy/).
    """
    env_policy = os.environ.get("LABTRUST_POLICY_DIR")
    if env_policy:
        p = Path(env_policy).resolve()
        if not p.exists():
            raise PolicyPathError(
                f"LABTRUST_POLICY_DIR={env_policy!r} does not exist; set to a valid policy directory."
            )
        if not p.is_dir():
            raise PolicyPathError(
                f"LABTRUST_POLICY_DIR={env_policy!r} is not a directory; set to a valid policy directory."
            )
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
    if (repo / "policy").is_dir() and (repo / "policy" / "emits").exists():
        return repo
    raise PolicyPathError(
        "Policy directory not found: no policy/ with policy/emits/ under current or parent directory, "
        "and LABTRUST_POLICY_DIR not set. Run from repo root or set LABTRUST_POLICY_DIR to the policy directory."
    )
