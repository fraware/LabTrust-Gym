"""
Prompt registry loader and fingerprinting.

- load_prompt(prompt_id, version=None, repo_root=None) -> templates dict
  (system_template, developer_template, user_template, prompt_id, prompt_version).
  Default prompt_id/version from policy/llm/defaults.yaml or code default.
- compute_prompt_fingerprint(prompt_id, prompt_version, partner_id,
  policy_fingerprint, agent_id, role_id, timing_mode) -> sha256 hex (stable).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml


DEFAULT_PROMPT_ID = "ops_v2"
DEFAULT_PROMPT_VERSION = "2.0.0"
PROMPT_REGISTRY_FILENAME = "prompt_registry.v0.1.yaml"
DEFAULTS_FILENAME = "defaults.yaml"
ROLE_TO_PROMPT_FILENAME = "role_to_prompt.v0.1.yaml"


def _get_repo_root(repo_root: Path | None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    from labtrust_gym.config import get_repo_root

    return get_repo_root()


def load_defaults(repo_root: Path | None = None) -> tuple[str, str]:
    """
    Load default prompt_id and version from policy/llm/defaults.yaml.
    Returns (prompt_id, version). Falls back to (DEFAULT_PROMPT_ID,
    DEFAULT_PROMPT_VERSION) if file missing or invalid.
    """
    root = _get_repo_root(repo_root)
    path = root / "policy" / "llm" / DEFAULTS_FILENAME
    if not path.exists():
        return (DEFAULT_PROMPT_ID, DEFAULT_PROMPT_VERSION)
    try:
        data = load_yaml(path)
    except PolicyLoadError:
        return (DEFAULT_PROMPT_ID, DEFAULT_PROMPT_VERSION)
    pid = data.get("prompt_id")
    ver = data.get("version")
    return (
        str(pid) if pid is not None else DEFAULT_PROMPT_ID,
        str(ver) if ver is not None else DEFAULT_PROMPT_VERSION,
    )


def load_prompt(
    prompt_id: str | None = None,
    version: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Load prompt templates from policy/llm/prompt_registry.v0.1.yaml.

    If prompt_id or version is None, uses policy/llm/defaults.yaml (or code default).
    Returns dict with keys: system_template, developer_template, user_template,
    prompt_id, prompt_version. Raises PolicyLoadError if registry missing or
    no matching entry.
    """
    root = _get_repo_root(repo_root)
    if prompt_id is None or version is None:
        default_id, default_ver = load_defaults(root)
        prompt_id = prompt_id or default_id
        version = version or default_ver

    registry_path = root / "policy" / "llm" / PROMPT_REGISTRY_FILENAME
    if not registry_path.exists():
        raise PolicyLoadError(registry_path, "prompt registry file not found")
    data = load_yaml(registry_path)
    prompts = data.get("prompts")
    if not isinstance(prompts, list):
        raise PolicyLoadError(registry_path, "prompts must be a list")

    for entry in prompts:
        if not isinstance(entry, dict):
            continue
        if entry.get("prompt_id") == prompt_id and entry.get("version") == version:
            system = entry.get("system_template")
            developer = entry.get("developer_template")
            user = entry.get("user_template")
            if system is None or developer is None or user is None:
                raise PolicyLoadError(
                    registry_path,
                    f"prompt {prompt_id!r}@{version!r} missing required template fields",
                )
            return {
                "system_template": str(system).strip("\n"),
                "developer_template": str(developer).strip("\n"),
                "user_template": str(user).strip("\n"),
                "prompt_id": prompt_id,
                "prompt_version": version,
            }

    raise PolicyLoadError(
        registry_path,
        f"no prompt entry for prompt_id={prompt_id!r} version={version!r}",
    )


def get_prompt_id_for_role(role_id: str, repo_root: Path | None = None) -> str:
    """
    Resolve prompt_id for a role_id from policy/llm/role_to_prompt.v0.1.yaml.

    Dynamic at runtime so shift-change (UPDATE_ROSTER) can change role_id and thus prompt_id.
    Returns default_prompt_id from file (or DEFAULT_PROMPT_ID) if role_id unmapped.
    """
    root = _get_repo_root(repo_root)
    path = root / "policy" / "llm" / ROLE_TO_PROMPT_FILENAME
    if not path.exists():
        return DEFAULT_PROMPT_ID
    try:
        data = load_yaml(path)
    except PolicyLoadError:
        return DEFAULT_PROMPT_ID
    mapping = data.get("mapping")
    if isinstance(mapping, dict) and role_id and role_id in mapping:
        return str(mapping[role_id])
    default = data.get("default_prompt_id")
    return str(default) if default else DEFAULT_PROMPT_ID


def compute_prompt_fingerprint(
    prompt_id: str,
    prompt_version: str,
    partner_id: str = "",
    policy_fingerprint: str | None = None,
    agent_id: str = "",
    role_id: str = "",
    timing_mode: str = "explicit",
) -> str:
    """
    Canonical JSON of (prompt_id, prompt_version, partner_id,
    policy_fingerprint, agent_id, role_id, timing_mode) then SHA-256 hex.
    Stable across runs for same inputs.
    """
    payload = {
        "prompt_id": str(prompt_id),
        "prompt_version": str(prompt_version),
        "partner_id": str(partner_id),
        "policy_fingerprint": str(policy_fingerprint or ""),
        "agent_id": str(agent_id),
        "role_id": str(role_id),
        "timing_mode": str(timing_mode).strip().lower(),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
