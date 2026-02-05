"""
Tool proxy: gate LLM/agent tool calls against the signed Tool Registry (B010).

When an action carries tool_id, validate against the registry and (optional) role
allow-list before the event reaches the engine. The engine also gates at step();
this layer provides early feedback and a single place to extend (e.g. strict_signatures
checks on registry file or tool artifacts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from labtrust_gym.tools.registry import (
    check_tool_allowed,
    load_tool_registry,
    get_tool_entry,
    TOOL_NOT_IN_REGISTRY,
    TOOL_NOT_ALLOWED_FOR_ROLE,
)


def validate_tool_call(
    tool_id: str,
    registry: Dict[str, Any],
    agent_id: Optional[str] = None,
    role_id: Optional[str] = None,
    allowed_tools: Optional[list[str]] = None,
) -> Tuple[bool, Optional[str]]:
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


def ensure_tool_registry(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load tool registry from repo; return empty dict if missing. For use by agent/shield when building events."""
    return load_tool_registry(repo_root or Path("."))


def get_tool_capabilities(registry: Dict[str, Any], tool_id: str) -> list[str]:
    """Return declared capabilities for tool_id (empty list if not in registry)."""
    entry = get_tool_entry(registry, tool_id)
    if entry is None:
        return []
    caps = entry.get("capabilities")
    return list(caps) if isinstance(caps, list) else []
