"""
LabTrustEnvAdapter: interface for the golden runner and env wrappers.

Defined in engine to avoid circular import: core_env implements this interface
and must not depend on runner. Runner and other packages import the interface
from here or from runner.adapter (re-export).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from labtrust_gym.engine.event import StepEventDict
from labtrust_gym.engine.state import InitialStateDict


class LabTrustEnvAdapter(ABC):
    """
    Interface that the simulator must implement for the golden runner.

    Golden runner is the oracle; the engine is a black box that must return
    enough structured data for the oracle to normalize and assert.

    Implementations: CoreEnv, PZParallelAdapter. Do not instantiate base.
    """

    @abstractmethod
    def reset(
        self,
        initial_state: InitialStateDict | dict[str, Any],
        *,
        deterministic: bool,
        rng_seed: int,
    ) -> None:
        """Reset the simulator to the scenario initial state."""
        ...

    @abstractmethod
    def step(self, event: StepEventDict | dict[str, Any]) -> dict[str, Any]:
        """
        Apply one event.

        Must return a dict containing at minimum:
          - status: "ACCEPTED" | "BLOCKED"
          - emits: [str] (optional; empty list if none)
          - violations: list of {invariant_id, status, reason_code?, message?}
          - blocked_reason_code: str|None (required if status == BLOCKED)
          - token_consumed: [token_id] (optional)
          - hashchain: {head_hash, length, last_event_hash} (required)
          - enforcements: list (optional)
          - (optional) state_snapshot: any data for assertions
        """
        ...

    @abstractmethod
    def query(self, expr: str) -> Any:
        """
        Query a computed property for state_assertions in the golden YAML.

        Example expr strings used in scenarios:
          - "queue_head(DEV_CHEM_A_01)"
          - "zone_state('Z_RESTRICTED_BIOHAZARD')"
          - "result_status('RES_QC1')"
          - "system_state('log_frozen')"
        """
        ...

    def step_batch(self, events: list[StepEventDict | dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Optional: apply multiple events in order. Default implementation
        calls step(e) for each e. Override for batch-optimized engines.
        """
        return [self.step(e) for e in events]
