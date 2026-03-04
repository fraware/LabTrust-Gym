"""
Deterministic scripted supervisor agent baseline (e.g. for supervisor_0).

Policy: if a result is held and eligible for override (override_eligible_result_ids
in observation) and override token is available, RELEASE_RESULT_OVERRIDE for the
first; else NOOP. Purely deterministic. Used for benchmarks when supervisor role
is not driven by LLM or coordination.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.envs.action_contract import ACTION_NOOP


def _scalar(x: Any, default: int = 0) -> int:
    """Extract int from obs value."""
    if x is None:
        return default
    if hasattr(x, "item"):
        return int(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return int(x.flat[0]) if hasattr(x, "flat") else int(x[0])
    return int(x)


class ScriptedSupervisorAgent:
    """
    Deterministic scripted supervisor agent.

    Policy: if override_eligible_result_ids is non-empty and token_count_override > 0,
    RELEASE_RESULT_OVERRIDE for the first with QC reason_code; else NOOP.
    """

    def act(
        self,
        observation: dict[str, Any],
        agent_id: str = "supervisor_0",
    ) -> tuple[int, dict[str, Any]]:
        """
        Return (action_index, action_info). action_index 0 with action_type
        override for RELEASE_RESULT_OVERRIDE when eligible; else NOOP.
        """
        action_info: dict[str, Any] = {
            "reason_code": "AGENT_SCRIPTED_NOOP",
            "rationale": "scripted_supervisor: no override eligible or no token",
        }
        override_eligible = observation.get("override_eligible_result_ids") or []
        token_override = _scalar(observation.get("token_count_override"), 0)
        if isinstance(override_eligible, (list, tuple)) and len(override_eligible) > 0 and token_override > 0:
            rid = str(override_eligible[0])
            return (
                ACTION_NOOP,
                {
                    "action_type": "RELEASE_RESULT_OVERRIDE",
                    "args": {"result_id": rid},
                    "reason_code": "QC_DRIFT_SUSPECTED",
                    "rationale": "scripted_supervisor: override release after review",
                },
            )
        return (ACTION_NOOP, action_info)
