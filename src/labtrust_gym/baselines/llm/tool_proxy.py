"""
Tool proxy: gate LLM/agent tool calls against the signed Tool Registry (B010).

When an action carries tool_id, validate against the registry and (optional) role
allow-list before the event reaches the engine. The engine also gates at step();
this layer provides early feedback and a single place to extend (e.g. strict_signatures
checks on registry file or tool artifacts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.tools.registry import (
    check_tool_allowed,
    get_tool_entry,
    load_tool_registry,
)


def validate_tool_call(
    tool_id: str,
    registry: dict[str, Any],
    agent_id: str | None = None,
    role_id: str | None = None,
    allowed_tools: list[str] | None = None,
) -> tuple[bool, str | None]:
    """
    Validate a tool call: tool must be in registry and (if allowed_tools set) in allow-list.
    Returns (allowed, reason_code). Use same reason codes as engine (TOOL_NOT_IN_REGISTRY, TOOL_NOT_ALLOWED_FOR_ROLE).
    """
    return check_tool_allowed(
        tool_id,
        registry,
        agent_id=agent_id,
        role_id=role_id,
        allowed_tools=allowed_tools,
    )


def ensure_tool_registry(repo_root: Path | None = None) -> dict[str, Any]:
    """Load tool registry from repo; return empty dict if missing. For use by agent/shield when building events."""
    return load_tool_registry(repo_root or Path("."))


def get_tool_capabilities(registry: dict[str, Any], tool_id: str) -> list[str]:
    """Return declared capabilities for tool_id (empty list if not in registry)."""
    entry = get_tool_entry(registry, tool_id)
    if entry is None:
        return []
    caps = entry.get("capabilities")
    return list(caps) if isinstance(caps, list) else []
