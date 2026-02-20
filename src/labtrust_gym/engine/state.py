"""
Typed shapes for the engine's initial state (reset input).

The engine's reset() accepts a plain dict. This module defines the expected keys
and types for that dict so that callers and tools can validate or document
the reset payload. All keys are optional at the type level; the runtime
fills defaults where needed.
"""

from __future__ import annotations

from typing import Any, TypedDict


class InitialStateDict(TypedDict, total=False):
    """
    Keys accepted by CoreEnv.reset(initial_state, ...).

    All keys are optional. The engine uses defaults when a key is missing.
    """

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
