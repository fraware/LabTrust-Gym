"""
Minimal example: runnable random policy agent implementing the LabTrustAgent protocol.

Uses a seeded RNG to choose between NOOP and TICK each step (policy-aware: NOOP when
log_frozen). Run with:

  labtrust eval-agent --task throughput_sla --episodes 2 --agent "examples.minimal_random_policy_agent:MinimalRandomAgent" --out out.json

When run as a script, prints the run command.
"""

from __future__ import annotations

import random
from typing import Any

from labtrust_gym.baselines.agent_api import LabTrustAgentBase

# Action indices aligned with pz_parallel (NOOP=0, TICK=1, QUEUE_RUN=2, ...)
ACTION_NOOP = 0
ACTION_TICK = 1

ACTION_INDEX_TO_NAME = {
    0: "NOOP",
    1: "TICK",
    2: "QUEUE_RUN",
    3: "MOVE",
    4: "OPEN_DOOR",
    5: "START_RUN",
}


class MinimalRandomAgent(LabTrustAgentBase):
    """
    Minimal but real agent: reset(seed, ...) initializes RNG; act(obs) returns NOOP or TICK
    at random (using seed for reproducibility). Respects log_frozen (NOOP when frozen).
    """

    def __init__(self) -> None:
        super().__init__()
        self._rng: random.Random | None = None
        self._last_action: int = ACTION_NOOP

    def reset(
        self,
        seed: int,
        policy_summary: dict[str, Any] | None = None,
        partner_id: str | None = None,
        timing_mode: str = "explicit",
    ) -> None:
        self._rng = random.Random(seed)
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
        if self._rng is None:
            self._rng = random.Random(42)
        self._last_action = self._rng.choice((ACTION_NOOP, ACTION_TICK))
        return self._last_action

    def explain_last_action(self) -> dict[str, Any] | None:
        """Override: return action info for logging."""
        return {
            "action_index": self._last_action,
            "action_type": ACTION_INDEX_TO_NAME.get(self._last_action, "NOOP"),
        }


if __name__ == "__main__":
    print(
        "Minimal random policy agent. Run with:\n"
        "  labtrust eval-agent --task throughput_sla --episodes 2 "
        '--agent "examples.minimal_random_policy_agent:MinimalRandomAgent" --out out.json'
    )
