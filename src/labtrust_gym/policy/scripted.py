"""
Load scripted baseline policy files (scripted_ops, scripted_runner).

When policy_path is None or file is missing, returns {} so agents use in-code defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root, policy_path
from labtrust_gym.policy.loader import (
    get_schema_path_for_file,
    load_yaml_optional,
    validate_against_schema,
)


def load_scripted_ops_policy(
    policy_path_arg: Path | None = None,
    repo_root: Path | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """
    Load scripted ops policy from YAML. Returns {} if path is None or file missing.
    """
    if policy_path_arg is not None:
        path = Path(policy_path_arg)
    else:
        try:
            root = repo_root or get_repo_root()
            path = policy_path(root, "scripted", "scripted_ops_policy.v0.1.yaml")
        except Exception:
            return {}
    data = load_yaml_optional(path, {})
    if not data or not isinstance(data, dict):
        return {}
    if validate:
        schemas_dir = path.parent.parent / "schemas"
        schema_path = get_schema_path_for_file(path, schemas_dir)
        if schema_path and schema_path.exists():
            try:
                import json

                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                validate_against_schema(data, schema, path)
            except Exception:
                pass
    return data


def load_scripted_runner_policy(
    policy_path_arg: Path | None = None,
    repo_root: Path | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """
    Load scripted runner policy from YAML. Returns {} if path is None or file missing.
    """
    if policy_path_arg is not None:
        path = Path(policy_path_arg)
    else:
        try:
            root = repo_root or get_repo_root()
            path = policy_path(root, "scripted", "scripted_runner_policy.v0.1.yaml")
        except Exception:
            return {}
    data = load_yaml_optional(path, {})
    if not data or not isinstance(data, dict):
        return {}
    if validate:
        schemas_dir = path.parent.parent / "schemas"
        schema_path = get_schema_path_for_file(path, schemas_dir)
        if schema_path and schema_path.exists():
            try:
                import json

                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                validate_against_schema(data, schema, path)
            except Exception:
                pass
    return data
