"""Structural validation for policy/pcs/*.yaml (validate-policy integration)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from labtrust_gym.config import policy_path
from labtrust_gym.pcs.integrity import REQUIRED_REASON_CODES, REQUIRED_ROLES


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be a mapping")
    return data


def validate_pcs_policy_files(root: Path) -> list[str]:
    errors: list[str] = []
    roles_path = policy_path(root, "pcs", "roles.yaml")
    reasons_path = policy_path(root, "pcs", "reason_codes.yaml")
    policy_path_file = policy_path(root, "pcs", "qc_release_policy.yaml")

    for path in (roles_path, reasons_path, policy_path_file):
        if not path.is_file():
            errors.append(f"{path}: missing")
            return errors

    try:
        roles_doc = _load_yaml(roles_path)
        reasons_doc = _load_yaml(reasons_path)
        qc_doc = _load_yaml(policy_path_file)
    except (yaml.YAMLError, ValueError) as e:
        errors.append(str(e))
        return errors

    roles = roles_doc.get("roles", {})
    if not isinstance(roles, dict):
        errors.append(f"{roles_path}: roles must be a mapping")
    else:
        for role_id in REQUIRED_ROLES:
            if role_id not in roles:
                errors.append(f"{roles_path}: missing role {role_id!r}")
        release_capable = [rid for rid, r in roles.items() if isinstance(r, dict) and r.get("release_capable")]
        if release_capable != ["release_manager"]:
            errors.append(f"{roles_path}: only release_manager may be release_capable, got {release_capable}")

    codes = reasons_doc.get("reason_codes", {})
    if not isinstance(codes, dict):
        errors.append(f"{reasons_path}: reason_codes must be a mapping")
    else:
        for code in REQUIRED_REASON_CODES:
            if code not in codes:
                errors.append(f"{reasons_path}: missing reason code {code!r}")

    required_actions = qc_doc.get("required_actions", [])
    expected_actions = [
        "accession_sample",
        "perform_qc",
        "record_analysis",
        "release_sample",
    ]
    for action in expected_actions:
        if action not in required_actions:
            errors.append(f"{policy_path_file}: required_actions missing {action!r}")

    return errors
