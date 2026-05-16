"""Load PCS demo policy (roles, reason codes, qc-release rules)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from labtrust_gym.config import get_repo_root, policy_path
from labtrust_gym.pcs.hash import pcs_digest

PCS_POLICY_DIR = ("pcs",)


@lru_cache(maxsize=1)
def load_roles(policy_root: Path | None = None) -> dict[str, Any]:
    root = policy_root or get_repo_root()
    path = policy_path(root, *PCS_POLICY_DIR, "roles.yaml")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_reason_codes(policy_root: Path | None = None) -> dict[str, Any]:
    root = policy_root or get_repo_root()
    path = policy_path(root, *PCS_POLICY_DIR, "reason_codes.yaml")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_qc_release_policy(policy_root: Path | None = None) -> dict[str, Any]:
    root = policy_root or get_repo_root()
    path = policy_path(root, *PCS_POLICY_DIR, "qc_release_policy.yaml")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def role_can_release(role_id: str, policy_root: Path | None = None) -> bool:
    roles_doc = load_roles(policy_root)
    role = roles_doc.get("roles", {}).get(role_id)
    if not role:
        return False
    return bool(role.get("release_capable", False))


def policy_hash(policy_root: Path | None = None) -> str:
    root = policy_root or get_repo_root()
    return pcs_digest(
        {
            "roles": load_roles(root),
            "reason_codes": load_reason_codes(root),
            "qc_release": load_qc_release_policy(root),
        }
    )
