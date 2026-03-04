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


_MAX_WALK_DEPTH = 20


def _find_repo_root() -> Path | None:
    """
    Walk up from cwd to find a directory containing policy/ with policy/emits/.
    Returns the first such directory, or None if not found within _MAX_WALK_DEPTH.
    """
    cwd = Path.cwd().resolve()
    current = cwd
    for _ in range(_MAX_WALK_DEPTH):
        if (current / "policy").is_dir() and (current / "policy" / "emits").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# Profile path fields that must resolve under policy_root (no arbitrary absolute paths).
RESTRICTED_PATH_FIELDS = frozenset({"security_suite_path", "safety_claims_path"})


def get_effective_path(
    policy_root: Path,
    profile: dict[str, Any] | None,
    field: str,
    default_relative: str,
    restrict_to_policy_root: bool | None = None,
) -> Path:
    """
    Resolve a path from the lab profile. If profile has a non-null value for field,
    interpret it as relative to policy_root (or absolute if it looks absolute);
    otherwise return policy_root / "policy" / default_relative.

    When restrict_to_policy_root is True (or when field is in RESTRICTED_PATH_FIELDS
    and restrict_to_policy_root is not False), the resolved path must be under
    policy_root; otherwise the default path is returned to prevent pointing at
    arbitrary files outside the repo.
    """
    base = policy_root / "policy"
    do_restrict = restrict_to_policy_root if restrict_to_policy_root is not None else (field in RESTRICTED_PATH_FIELDS)
    if profile and profile.get(field) not in (None, ""):
        raw = profile[field]
        if isinstance(raw, str):
            p = Path(raw)
            if p.is_absolute():
                resolved = p.resolve()
            else:
                resolved = (policy_root / raw).resolve()
            if do_restrict:
                try:
                    root_resolved = policy_root.resolve()
                    if not resolved.is_relative_to(root_resolved):
                        return base / default_relative
                except (ValueError, AttributeError):
                    return base / default_relative
            return resolved
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
    if repo is not None and (repo / "policy").is_dir() and (repo / "policy" / "emits").exists():
        return repo
    raise PolicyPathError(
        "Policy directory not found: no policy/ with policy/emits/ under current or parent directory, "
        "and LABTRUST_POLICY_DIR not set. Set LABTRUST_POLICY_DIR to the policy directory, "
        "run from repo root (or any subdirectory of the repo), or install from wheel so policy is loaded from package data."
    )


def get_policy_source() -> tuple[str, Path] | None:
    """
    Return (source, policy_dir) for diagnostics: "env" | "package" | "repo", and the policy directory path.
    Returns None if policy cannot be resolved (caller may then get_repo_root() to raise).
    """
    env_policy = os.environ.get("LABTRUST_POLICY_DIR")
    if env_policy:
        p = Path(env_policy).resolve()
        if p.exists() and p.is_dir():
            return ("env", p)
        return None
    try:
        from importlib.resources import files

        pkg_policy = files("labtrust_gym") / "policy"
        pkg_path = Path(str(pkg_policy))
        if pkg_path.is_dir() and (pkg_path / "emits").exists():
            return ("package", pkg_path)
    except Exception:
        pass
    repo = _find_repo_root()
    if repo is not None and (repo / "policy").is_dir() and (repo / "policy" / "emits").exists():
        return ("repo", repo / "policy")
    return None
