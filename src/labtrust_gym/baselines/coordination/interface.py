"""
Coordination method interface for PettingZoo Parallel env.

FROZEN CONTRACT (Coordination Baseline Contract v0.1): New methods must implement
this interface; CI enforces it via tests/test_coordination_interface_contract.py.

Required hooks:
  - reset(seed, policy, scale_config): called before first propose_actions each episode.
  - propose_actions(obs, infos, t) -> Dict[agent_id, action_dict]: one action per
    active agent; action_dict must contain "action_index" (int in 0..5) and may
    contain "action_type", "args", "reason_code", "token_refs".

Optional hooks (default no-op):
  - on_step_result(step_outputs): feedback after env.step (alias: observe).
  - on_episode_end(episode_metrics): called at end of episode (e.g. for learning).
  - get_learning_metadata(): when method is study-track (learning/evolving), return dict with
    enabled, checkpoint_sha, update_count, buffer_size for results.metadata.coordination.learning.

Each method produces per-agent actions compatible with the env API:
action_index (0=NOOP, 1=TICK, 2=QUEUE_RUN, 3=MOVE, 4=OPEN_DOOR, 5=START_RUN).
The runner builds a CoordDecision (contract record) per step; see
policy/schemas/coord_method_output_contract.v0.1.schema.json and telemetry.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

# CoordDecision: one timestep record per coord_method_output_contract.v0.1 (built in runner)
CoordDecision = dict[str, Any]

# Action indices aligned with pz_parallel (schema-valid range for action_index)
ACTION_NOOP = 0
ACTION_TICK = 1
ACTION_QUEUE_RUN = 2
ACTION_MOVE = 3
ACTION_OPEN_DOOR = 4
ACTION_START_RUN = 5
VALID_ACTION_INDICES = frozenset({0, 1, 2, 3, 4, 5})


def action_dict_to_index_and_info(
    action_dict: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """
    Convert action_dict from propose_actions to (action_index, action_info).
    action_info is passed to env as action_infos[agent_id]; must not include "action_index".
    """
    idx = int(action_dict.get("action_index", ACTION_NOOP))
    info = {k: v for k, v in action_dict.items() if k != "action_index" and v is not None}
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
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        """
        Reset method state for a new episode. Called before first propose_actions.
        policy: effective_policy or subset (rbac, zones, equipment). scale_config: sanitized.
        """
        pass

    @abstractmethod
    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        """
        Return one action per active agent. Keys = agent_id (PZ name, e.g. worker_0).
        Value = action_dict with at least "action_index" (int); optionally "action_type",
        "args", "reason_code", "token_refs" for engine event. Missing agents get NOOP.
        """
        ...

    def on_step_result(
        self,
        step_outputs: list[dict[str, Any]],
    ) -> None:
        """Optional: feedback after env.step (e.g. for learning or message delay)."""
        pass

    def on_episode_end(
        self,
        episode_metrics: dict[str, Any],
    ) -> None:
        """Optional: called at end of episode (e.g. for learning or logging)."""
        pass

    def get_learning_metadata(self) -> dict[str, Any] | None:
        """
        Optional: when this method is study-track (learning/evolving across episodes),
        return a dict for results.metadata.coordination.learning. Keys: enabled (bool),
        checkpoint_sha (str, optional), update_count (int, optional), buffer_size (int, optional).
        Return None for deterministic-track or inference-only methods.
        """
        return None
