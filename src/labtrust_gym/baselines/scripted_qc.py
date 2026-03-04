"""
Deterministic scripted QC agent baseline (e.g. for qc_0).

Policy: if there is at least one releasable result (engine already past QC),
RELEASE_RESULT for the first; else NOOP. Purely deterministic given observations.
Used for benchmarks when QC role is not driven by LLM or coordination.
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


class ScriptedQcAgent:
    """
    Deterministic scripted QC agent.

    Policy: if releasable_result_ids is non-empty, RELEASE_RESULT for the first
    (device QC pass is already enforced by engine for releasable list); else NOOP.
    """

    def act(
        self,
        observation: dict[str, Any],
        agent_id: str = "qc_0",
    ) -> tuple[int, dict[str, Any]]:
        """
        Return (action_index, action_info). action_index 0 with action_type
        override for RELEASE_RESULT; else NOOP.
        """
        action_info: dict[str, Any] = {
            "reason_code": "AGENT_SCRIPTED_NOOP",
            "rationale": "scripted_qc: no releasable results",
        }
        releasable = observation.get("releasable_result_ids") or []
        if not isinstance(releasable, (list, tuple)) or len(releasable) == 0:
            return (ACTION_NOOP, action_info)
        rid = str(releasable[0])
        return (
            ACTION_NOOP,
            {
                "action_type": "RELEASE_RESULT",
                "args": {"result_id": rid},
                "reason_code": None,
                "rationale": "scripted_qc: release first releasable result",
            },
        )
