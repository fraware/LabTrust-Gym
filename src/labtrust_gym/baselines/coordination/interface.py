"""
Coordination method interface for PettingZoo Parallel env.

Each method produces per-agent actions compatible with the existing env API:
action_index (0=NOOP, 1=TICK, 2=QUEUE_RUN, 3=MOVE, 4=OPEN_DOOR, 5=START_RUN)
and optional action_info (action_type, args, reason_code, token_refs) for engine events.

Contract v0.1: the runner builds a CoordDecision (contract record) per step from
method_id, t_step, actions, view_age_ms, and optional plan_time_ms, invariants_considered,
safety_shield_applied; see policy/schemas/coord_method_output_contract.v0.1.schema.json
and baselines/coordination/telemetry.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# CoordDecision: one timestep record per coord_method_output_contract.v0.1 (built in runner)
CoordDecision = Dict[str, Any]

# Action indices aligned with pz_parallel
ACTION_NOOP = 0
ACTION_TICK = 1
ACTION_QUEUE_RUN = 2
ACTION_MOVE = 3
ACTION_OPEN_DOOR = 4
ACTION_START_RUN = 5


def action_dict_to_index_and_info(
    action_dict: Dict[str, Any],
) -> tuple[int, Dict[str, Any]]:
    """
    Convert action_dict from propose_actions to (action_index, action_info).
    action_info is passed to env as action_infos[agent_id]; must not include "action_index".
    """
    idx = int(action_dict.get("action_index", ACTION_NOOP))
    info = {
        k: v for k, v in action_dict.items() if k != "action_index" and v is not None
    }
    return idx, info


class CoordinationMethod(ABC):
    """
    Base interface for coordination methods. Deterministic in deterministic backend mode.
    """

    @property
    @abstractmethod
    def method_id(self) -> str:
        """Registry method_id (e.g. centralized_planner)."""
        ...

    def reset(
        self,
        seed: int,
        policy: Dict[str, Any],
        scale_config: Dict[str, Any],
    ) -> None:
        """
        Reset method state for a new episode. Called before first propose_actions.
        policy: effective_policy or subset (rbac, zones, equipment). scale_config: sanitized.
        """
        pass

    @abstractmethod
    def propose_actions(
        self,
        obs: Dict[str, Any],
        infos: Dict[str, Dict[str, Any]],
        t: int,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Return one action per active agent. Keys = agent_id (PZ name, e.g. worker_0).
        Value = action_dict with at least "action_index" (int); optionally "action_type",
        "args", "reason_code", "token_refs" for engine event. Missing agents get NOOP.
        """
        ...

    def on_step_result(
        self,
        step_outputs: List[Dict[str, Any]],
    ) -> None:
        """Optional: feedback after env.step (e.g. for learning or message delay)."""
        pass
