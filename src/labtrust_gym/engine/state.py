"""
Typed shapes for engine initial state (reset input).

Used for documentation and optional validation. The engine accepts
dict[str, Any]; this module defines the expected keys for core_env.reset().
"""

from __future__ import annotations

from typing import Any, TypedDict


class InitialStateDict(TypedDict, total=False):
    """Keys for CoreEnv.reset(initial_state, ...). All optional at type level."""

    audit_fault_injection: dict[str, Any] | None
    system: dict[str, Any]
    tokens: list[Any]
    effective_policy: dict[str, Any] | None
    zone_layout: dict[str, Any] | None
    _scale_config_sanitized: Any
    agents: list[dict[str, Any]]
    specimens: list[Any]
    timing_mode: str
    policy_root: str | None
    reagent_initial_stock: dict[str, int | float] | None
    enforcement_enabled: bool
    transport_fault_injection: dict[str, Any] | None
    strict_signatures: bool
    partner_id: str | None
    policy_fingerprint: str | None
    tool_registry: dict[str, Any]
    allowed_tools: list[str] | None
    tool_adapter: Any
    tool_timeout_s: float | None
    state_label: str | None
    state_tool_capability_map: dict[str, Any] | None
