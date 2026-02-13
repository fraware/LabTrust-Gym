"""
Example external agent using the LabTrustAgent protocol.

SafeNoOpAgent: policy-aware trivial agent that does NOOP or TICK only.
Use with: labtrust eval-agent --task TaskA --episodes 2 --agent "examples.external_agent_demo:SafeNoOpAgent" --out results.json
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.agent_api import LabTrustAgentBase

# Action indices aligned with pz_parallel (NOOP=0, TICK=1, ...)
ACTION_NOOP = 0
ACTION_TICK = 1


class SafeNoOpAgent(LabTrustAgentBase):
    """
    Trivial safe agent: reset(seed, ...) stores config; act(obs) returns NOOP or TICK.

    Policy-aware in the sense that it respects log_frozen (NOOP when frozen)
    and can TICK when door_restricted_open; otherwise NOOP.
    """

    def __init__(self) -> None:
        super().__init__()
        self._seed: int | None = None
        self._timing_mode: str = "explicit"
        self._last_action: int = ACTION_NOOP

    def reset(
        self,
        seed: int,
        policy_summary: dict[str, Any] | None = None,
        partner_id: str | None = None,
        timing_mode: str = "explicit",
    ) -> None:
        self._seed = seed
        self._timing_mode = (timing_mode or "explicit").strip().lower()
        self._last_action = ACTION_NOOP

    def act(self, observation: dict[str, Any]) -> int:
        if not isinstance(observation, dict):
            self._last_action = ACTION_NOOP
            return ACTION_NOOP
        log_frozen = observation.get("log_frozen")
        if log_frozen is not None:
            try:
                v = int(log_frozen) if not hasattr(log_frozen, "item") else int(log_frozen.item())
            except (TypeError, ValueError):
                v = 0
            if v:
                self._last_action = ACTION_NOOP
                return ACTION_NOOP
        door_open = observation.get("door_restricted_open")
        if door_open is not None:
            try:
                v = int(door_open) if not hasattr(door_open, "item") else int(door_open.item())
            except (TypeError, ValueError):
                v = 0
            if v:
                self._last_action = ACTION_TICK
                return ACTION_TICK
        self._last_action = ACTION_NOOP
        return ACTION_NOOP

    def explain_last_action(self) -> dict[str, Any] | None:
        """Override: return action info for logging."""
        return {
            "action_index": self._last_action,
            "action_type": "TICK" if self._last_action == ACTION_TICK else "NOOP",
        }


def create_safe_noop_agent() -> SafeNoOpAgent:
    """Factory function for loader: module:function returns instance."""
    return SafeNoOpAgent()
