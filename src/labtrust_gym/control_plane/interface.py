"""
Control-plane interface: gate_decision and enforcement_actions.

ControlPlane.apply(event, context) -> gate_decision, enforcement_actions.
Used by the engine to run first gates (RBAC, tokens, signatures) and post-step enforcement
without duplicating contract semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class GateDecision:
    """
    Result of control-plane gates (RBAC, capability, signature).
    When allowed=False, step_output_fragment contains status=BLOCKED, blocked_reason_code, etc.
    When allowed=True, step_output_fragment contains rbac_decision, signature_verification to merge.
    """

    allowed: bool
    step_output_fragment: dict[str, Any] = field(default_factory=dict)

    def to_step_output(self) -> dict[str, Any]:
        """Fragment to merge into engine step result (no hashchain; engine adds that)."""
        return dict(self.step_output_fragment)


@runtime_checkable
class ControlPlane(Protocol):
    """
    Control-plane protocol: apply(event, context) -> gate_decision, enforcement_actions.
    First gates run before any data-plane mutation; enforcement runs post-step.
    """

    def apply(
        self,
        event: dict[str, Any],
        context: dict[str, Any],
    ) -> GateDecision:
        """
        Run first gates on event. Returns GateDecision; when allowed=False,
        step_output_fragment has status BLOCKED and blocked_reason_code.
        """
        ...

    def apply_enforcement(
        self,
        step_result: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Post-step enforcement: given step result (violations, etc.), return
        list of enforcement actions (throttle_agent, kill_switch, etc.).
        """
        ...
