"""
Typed shape for engine step event (step input).

Used for documentation and optional validation. The engine accepts
dict[str, Any]; this module defines the expected keys for core_env.step(event).
"""

from __future__ import annotations

from typing import Any, TypedDict


class StepEventDict(TypedDict, total=False):
    """Keys accepted by CoreEnv.step(event). All optional at type level."""

    event_id: str
    t_s: int
    agent_id: str
    action_type: str
    args: dict[str, Any]
    token_refs: list[Any]
    tool_id: str | None
    key_id: str | None
    signature: str | None
    reason_code: str | None
