"""
Tool registry: load, validate, fingerprint, and gate tool calls.

Agent may only call tools that exist in the signed Tool Registry with pinned
versions and declared capabilities. Covers: Unverified Tool Risk, Tool
Vulnerability Exploitation Risk (pinning + SBOM), Unauthorized use (scoped
capability gating).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Reason codes (must exist in policy/reason_codes/reason_code_registry.v0.1.yaml)
TOOL_NOT_IN_REGISTRY = "TOOL_NOT_IN_REGISTRY"
TOOL_NOT_ALLOWED_FOR_ROLE = "TOOL_NOT_ALLOWED_FOR_ROLE"


def _registry_path_from_root(root: Path) -> Path:
    """Return path to policy/tool_registry.v0.1.yaml under root."""
    return Path(root) / "policy" / "tool_registry.v0.1.yaml"


def load_tool_registry(root_or_path: Path | None = None) -> dict[str, Any]:
    """
    Load tool registry YAML. If root_or_path is a directory, load
    policy/tool_registry.v0.1.yaml; if a file, load that path.
    Returns {"tool_registry": {"version", "tools": [...]}} or empty dict if missing.
    """
    if root_or_path is None:
        return {}
    path = Path(root_or_path)
    if path.is_dir():
        path = _registry_path_from_root(path)
    if not path.exists():
        return {}
    try:
        from labtrust_gym.policy.loader import load_yaml

        data = load_yaml(path)
    except Exception:
        return {}
    if not isinstance(data, dict) or "tool_registry" not in data:
        return {}
    return data


def tool_registry_fingerprint(registry_or_path: dict[str, Any] | Path) -> str:
    """
    Compute SHA-256 (hex) digest of the tool registry for reproducibility
    and EvidenceBundle. Input: loaded registry dict (with "tool_registry" key)
    or Path to YAML. Same content => same digest.
    """
    if isinstance(registry_or_path, Path):
        data = load_tool_registry(registry_or_path)
    else:
        data = dict(registry_or_path) if registry_or_path else {}
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_registry_hashes(
    registry: dict[str, Any],
    expected_hashes: dict[str, str] | None = None,
) -> list[str]:
    """
    Validate that each tool entry's sha256 (or wheel_hash) matches expected_hashes when provided.
    expected_hashes: optional dict tool_id -> expected_sha256_hex.
    Returns list of error messages; empty if valid.
    """
    errors: list[str] = []
    tr = registry.get("tool_registry") if isinstance(registry, dict) else {}
    tools = tr.get("tools") if isinstance(tr, dict) else []
    if not isinstance(tools, list):
        return ["tool_registry.tools must be an array"]
    if not expected_hashes:
        return []
    by_id = {t.get("tool_id"): t for t in tools if isinstance(t, dict) and t.get("tool_id")}
    for tool_id, expected in expected_hashes.items():
        if not tool_id or not expected:
            continue
        t = by_id.get(tool_id)
        if not t:
            errors.append(f"tool_id {tool_id!r} in expected_hashes not in registry")
            continue
        actual = t.get("sha256") or t.get("wheel_hash")
        if actual is None:
            continue
        if actual.strip().lower() != expected.strip().lower():
            errors.append(f"tool_id {tool_id!r}: registry hash {actual!r} does not match expected {expected!r}")
    return errors


def get_tool_entry(registry: dict[str, Any], tool_id: str) -> dict[str, Any] | None:
    """Return the registry entry for tool_id or None."""
    tr = registry.get("tool_registry") if isinstance(registry, dict) else {}
    tools = tr.get("tools") if isinstance(tr, dict) else []
    if not isinstance(tools, list):
        return None
    for t in tools:
        if isinstance(t, dict) and t.get("tool_id") == tool_id:
            return t
    return None


def check_tool_allowed(
    tool_id: str,
    registry: dict[str, Any],
    agent_id: str | None = None,
    role_id: str | None = None,
    allowed_tools: list[str] | None = None,
) -> tuple[bool, str | None]:
    """
    Check whether a tool call is allowed: tool must be in registry and (if
    allowed_tools is set) in the scenario/role allow-list.
    Returns (allowed, reason_code). reason_code is TOOL_NOT_IN_REGISTRY or
    TOOL_NOT_ALLOWED_FOR_ROLE when blocked.
    """
    if not tool_id or not isinstance(tool_id, str):
        return False, TOOL_NOT_IN_REGISTRY
    entry = get_tool_entry(registry, tool_id)
    if entry is None:
        return False, TOOL_NOT_IN_REGISTRY
    if allowed_tools is not None and len(allowed_tools) > 0:
        if tool_id not in allowed_tools:
            return False, TOOL_NOT_ALLOWED_FOR_ROLE
    return True, None


def combined_policy_fingerprint(
    policy_fingerprint: str,
    tool_registry_fingerprint_value: str | None = None,
    rbac_policy_fingerprint_value: str | None = None,
) -> str:
    """
    Combine policy fingerprint with tool registry and RBAC policy digests for
    EvidenceBundle and metadata. Order: policy_fp, rbac_fp, tool_registry_fp.
    When none of the optional fingerprints are present, returns policy_fingerprint.
    """
    parts = [policy_fingerprint]
    if rbac_policy_fingerprint_value:
        parts.append(rbac_policy_fingerprint_value)
    if tool_registry_fingerprint_value:
        parts.append(tool_registry_fingerprint_value)
    if len(parts) == 1:
        return policy_fingerprint
    payload = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_registry_sbom(
    registry: dict[str, Any],
    policy_root: Path | None = None,
    require_sbom: bool = False,
) -> list[str]:
    """
    Validate tool registry for optional SBOM/attestation provenance (v0.2).
    When require_sbom is True, every tool must have sbom_ref set.
    For tools with sbom_ref, attestation_ref, or cve_scan_ref, check that the path/URI exists
    when policy_root is set (local paths resolved relative to policy_root).
    Returns list of error messages; empty if valid.
    """
    errors: list[str] = []
    tr = registry.get("tool_registry") if isinstance(registry, dict) else {}
    tools = tr.get("tools") if isinstance(tr, dict) else []
    if not isinstance(tools, list):
        return ["tool_registry.tools must be an array"]
    root = Path(policy_root) if policy_root else None
    for t in tools:
        if not isinstance(t, dict):
            continue
        tool_id = t.get("tool_id") or "<unknown>"
        if require_sbom and not t.get("sbom_ref"):
            errors.append(f"tool_id {tool_id!r}: require_sbom is true but sbom_ref is missing")
        for key in ("sbom_ref", "attestation_ref", "cve_scan_ref"):
            ref = t.get(key)
            if not ref or not isinstance(ref, str):
                continue
            ref = ref.strip()
            if not ref:
                continue
            if root and not ref.startswith(("http://", "https://", "urn:")):
                local_path = (root / ref).resolve()
                if not local_path.exists():
                    errors.append(f"tool_id {tool_id!r}: {key} path {ref!r} does not exist")
    return errors
