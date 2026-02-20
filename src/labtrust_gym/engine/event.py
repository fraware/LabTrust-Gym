"""
Typed shape for a single step event (input to the engine step).

The engine's step() accepts a plain dict. This module defines the expected keys
and types so that callers and tools can validate or document the event payload.
All keys are optional at the type level.
"""

from __future__ import annotations

from typing import Any, TypedDict


class StepEventDict(TypedDict, total=False):
    """
    Keys accepted by CoreEnv.step(event).

    Includes event_id, time, agent_id, action_type, args, token refs,
    optional tool/signature/reason_code. All optional at type level.
    """

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
