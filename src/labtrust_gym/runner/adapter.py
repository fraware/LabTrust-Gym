"""LabTrustEnvAdapter: interface that the simulator must implement for the golden runner."""

from __future__ import annotations

from typing import Any, Dict


class LabTrustEnvAdapter:
    """
    Your simulator should implement this thin interface.

    Key design rule:
      - The golden runner is the oracle. The engine is a black box that must return enough
        structured data for the oracle to normalize and assert.
    """

    def reset(
        self, initial_state: Dict[str, Any], *, deterministic: bool, rng_seed: int
    ) -> None:
        """Reset the simulator to the scenario initial state."""
        raise NotImplementedError

    def step(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply one event.

        Must return a dict containing at minimum:
          - status: "ACCEPTED" | "BLOCKED"
          - emits: [str] (optional; empty list if none)
          - violations: list of {invariant_id, status, reason_code?, message?} (optional)
          - blocked_reason_code: str|None (required if status == BLOCKED)
          - token_consumed: [token_id] (optional)
          - hashchain: {head_hash, length, last_event_hash} (required)
          - enforcements: list of {type, target?, duration_s?, reason_code?, rule_id?} (optional)
          - (optional) state_snapshot: any data you want to expose for assertions
        """
        raise NotImplementedError

    def query(self, expr: str) -> Any:
        """
        Query a computed property for state_assertions in the golden YAML.

        Example expr strings used in scenarios:
          - "queue_head(DEV_CHEM_A_01)"
          - "zone_state('Z_RESTRICTED_BIOHAZARD')"
          - "result_status('RES_QC1')"
          - "system_state('log_frozen')"
        """
        raise NotImplementedError
