"""
Capabilities vocabulary and tool-registry validation.

- capabilities.v0.1.yaml: controlled vocabulary of capability IDs.
- Tool registry capabilities must be a subset of that vocabulary.
- validate_capabilities(registry, cap_vocab) returns list of error messages.
- State-tool capability map: state_label -> allowed_capabilities for tool-selection error detection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import load_yaml


def load_capabilities_vocab(path: Path | str) -> set[str]:
    """
    Load capabilities vocabulary from policy/capabilities.v0.1.yaml.
    Returns set of capability_ids. Path may be directory (policy root) or file.
    """
    p = Path(path)
    if p.is_dir():
        p = p / "policy" / "capabilities.v0.1.yaml"
    if not p.exists():
        return set()
    data = load_yaml(p)
    root = data.get("capabilities")
    if not isinstance(root, dict):
        return set()
    raw = root.get("capability_ids")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if x is not None and str(x).strip()}


def validate_capabilities(
    registry: dict[str, Any],
    cap_vocab: set[str],
) -> list[str]:
    """
    Validate that every tool's capabilities in the registry are a subset of cap_vocab.
    registry: loaded tool registry dict (with "tool_registry" -> "tools").
    cap_vocab: set of allowed capability IDs from capabilities.v0.1.yaml.
    Returns list of error messages; empty if valid.
    """
    errors: list[str] = []
    tr = registry.get("tool_registry") if isinstance(registry, dict) else {}
    tools = tr.get("tools") if isinstance(tr, dict) else []
    if not isinstance(tools, list):
        return ["tool_registry.tools must be an array"]
    for t in tools:
        if not isinstance(t, dict):
            continue
        tool_id = t.get("tool_id")
        if not tool_id:
            continue
        caps = t.get("capabilities")
        if not isinstance(caps, list):
            continue
        for cap in caps:
            if cap is None or not str(cap).strip():
                continue
            cap_str = str(cap).strip()
            if cap_vocab and cap_str not in cap_vocab:
                errors.append(f"tool_id {tool_id!r}: capability {cap_str!r} not in capabilities vocabulary")
    return errors


def load_state_tool_capability_map(path: Path | str) -> dict[str, list[str]]:
    """
    Load state_tool_capability_map.v0.1.yaml. Returns state_label -> list of
    allowed_capability IDs. Path may be directory (policy root) or file.
    """
    p = Path(path)
    if p.is_dir():
        p = p / "policy" / "state_tool_capability_map.v0.1.yaml"
    if not p.exists():
        return {}
    data = load_yaml(p)
    root = data.get("state_tool_capability_map")
    if not isinstance(root, dict):
        return {}
    labels = root.get("state_labels")
    if not isinstance(labels, dict):
        return {}
    out: dict[str, list[str]] = {}
    for state_label, entry in labels.items():
        if not isinstance(entry, dict):
            continue
        allowed = entry.get("allowed_capabilities")
        if isinstance(allowed, list):
            out[str(state_label)] = [str(x) for x in allowed if x is not None]
    return out


def get_allowed_capabilities_for_state(
    state_label: str | None,
    state_map: dict[str, list[str]],
) -> list[str] | None:
    """
    Return allowed capability IDs for the given state_label. If state_label is
    None or not in map, returns state_map.get("default"). If no default, returns None
    (interpret as: no state-based restriction, or all capabilities allowed by registry).
    """
    if not state_map:
        return None
    if state_label and state_label in state_map:
        return list(state_map[state_label])
    return state_map.get("default")
