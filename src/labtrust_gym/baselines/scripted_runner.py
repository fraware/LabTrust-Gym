"""
Deterministic scripted runner/robot baseline: physical steps (MOVE, TICK, OPEN_DOOR, START_RUN).

Policy: colocation for device ops; reception -> centrifuge -> aliquot -> analyzer queue -> start_run;
never opens restricted door without token; respects frozen zones; calls TICK to advance door timers.
Purely deterministic given observations.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

from labtrust_gym.engine.zones import (
    build_adjacency_set,
    get_default_device_zone_map,
)

# Zone order must match env's zone list for my_zone_idx (1-based index)
DEFAULT_ZONE_IDS: List[str] = [
    "Z_SRA_RECEPTION",
    "Z_ACCESSIONING",
    "Z_SORTING_LANES",
    "Z_PREANALYTICS",
    "Z_CENTRIFUGE_BAY",
    "Z_ALIQUOT_LABEL",
    "Z_ANALYZER_HALL_A",
    "Z_ANALYZER_HALL_B",
    "Z_QC_SUPERVISOR",
    "Z_RESTRICTED_BIOHAZARD",
]

# Action indices aligned with pz_parallel (runner uses 0,1,3,4,5; ops uses 0,1,2)
ACTION_NOOP = 0
ACTION_TICK = 1
ACTION_QUEUE_RUN = 2  # ops only
ACTION_MOVE = 3
ACTION_OPEN_DOOR = 4
ACTION_START_RUN = 5

# Default zone order for workflow: reception area -> centrifuge -> aliquot -> analyzer
DEFAULT_WORKFLOW_ZONES: List[str] = [
    "Z_SORTING_LANES",
    "Z_CENTRIFUGE_BAY",
    "Z_ALIQUOT_LABEL",
    "Z_ANALYZER_HALL_A",
    "Z_ANALYZER_HALL_B",
]

RESTRICTED_ZONE_ID = "Z_RESTRICTED_BIOHAZARD"
RESTRICTED_DOOR_ID = "D_RESTRICTED_AIRLOCK"


def _scalar(x: Any, default: int = 0) -> int:
    """Extract int from obs value."""
    if x is None:
        return default
    if hasattr(x, "item"):
        return int(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return int(x.flat[0]) if hasattr(x, "flat") else int(x[0])
    return int(x)


def _float_scalar(x: Any, default: float = 0.0) -> float:
    """Extract float from obs value."""
    if x is None:
        return default
    if hasattr(x, "item"):
        return float(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return float(x.flat[0]) if hasattr(x, "flat") else float(x[0])
    return float(x)


def _queue_has_head(obs: Dict[str, Any], device_idx: int) -> bool:
    """True if device at index has queue head."""
    arr = obs.get("queue_has_head")
    if arr is None:
        return False
    if hasattr(arr, "flat"):
        return bool(arr.flat[device_idx] if device_idx < arr.size else 0)
    if isinstance(arr, (list, tuple)) and device_idx < len(arr):
        return bool(arr[device_idx])
    return False


def _bfs_one_step(
    start: str,
    goal: str,
    adjacency: Set[Tuple[str, str]],
) -> Optional[str]:
    """Return one step (next zone) from start toward goal along graph, or None."""
    if start == goal:
        return None
    seen: Set[str] = {start}
    queue: deque[Tuple[str, List[str]]] = deque([(start, [])])
    while queue:
        node, path = queue.popleft()
        neighbors = [b for (a, b) in adjacency if a == node and b not in seen]
        for n in sorted(neighbors):
            seen.add(n)
            new_path = path + [n]
            if n == goal:
                return new_path[0]
            queue.append((n, new_path))
    return None


class ScriptedRunnerAgent:
    """
    Deterministic scripted runner: colocation, workflow MOVE, TICK, OPEN_DOOR, START_RUN.

    Policy:
      1) Keeps itself in correct zones for device operations (colocation).
      2) Fetches reception -> centrifuge -> aliquot -> analyzer queue -> start_run.
      3) Never opens restricted doors without token; respects frozen zones.
      4) Calls TICK periodically to advance door timers (when door open too long).
    """

    def __init__(
        self,
        zone_ids: Optional[List[str]] = None,
        adjacency_set: Optional[Set[Tuple[str, str]]] = None,
        device_zone_map: Optional[Dict[str, str]] = None,
        device_ids: Optional[List[str]] = None,
        restricted_zone_id: str = RESTRICTED_ZONE_ID,
        restricted_door_id: str = RESTRICTED_DOOR_ID,
        door_tick_threshold_s: float = 150.0,
        tick_interval_steps: int = 3,
    ) -> None:
        from labtrust_gym.engine.zones import _default_layout as _layout

        layout = _layout()
        self._zone_ids = zone_ids or list(DEFAULT_ZONE_IDS)
        self._adjacency = adjacency_set or build_adjacency_set(
            layout.get("graph_edges", [])
        )
        self._device_zone = device_zone_map or get_default_device_zone_map()
        self._device_ids = device_ids or list(self._device_zone.keys())
        self._restricted_zone_id = restricted_zone_id
        self._restricted_door_id = restricted_door_id
        self._door_tick_threshold_s = door_tick_threshold_s
        self._tick_interval_steps = max(1, tick_interval_steps)
        self._step_counter = 0

    def _my_zone(self, obs: Dict[str, Any]) -> Optional[str]:
        """Current zone id from obs (my_zone_idx 1-based into zone_ids)."""
        idx = _scalar(obs.get("my_zone_idx"), 0)
        if idx < 1 or idx > len(self._zone_ids):
            return None
        return self._zone_ids[idx - 1]

    def _adjacent_zones(self, zone_id: str) -> List[str]:
        """Legal next zones (graph edges from zone_id). Sorted for determinism."""
        out = [b for (a, b) in self._adjacency if a == zone_id]
        return sorted(out)

    def act(
        self,
        observation: Dict[str, Any],
        agent_id: str = "runner_0",
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Return (action_index, action_info). Deterministic.

        action_index: 0=NOOP, 1=TICK, 3=MOVE, 4=OPEN_DOOR, 5=START_RUN.
        action_info: to_zone (MOVE), door_id (OPEN_DOOR), device_id/work_id (START_RUN).
        """
        self._step_counter += 1
        action_info: Dict[str, Any] = {}

        log_frozen = _scalar(observation.get("log_frozen"), 0)
        if log_frozen:
            return (ACTION_NOOP, action_info)

        restricted_frozen = _scalar(observation.get("restricted_zone_frozen"), 0)
        door_open = _scalar(observation.get("door_restricted_open"), 0)
        door_duration = _float_scalar(
            observation.get("door_restricted_duration_s"), 0.0
        )
        token_restricted = _scalar(observation.get("token_count_restricted"), 0)

        if door_open and door_duration >= self._door_tick_threshold_s:
            return (ACTION_TICK, action_info)

        if (
            self._step_counter % self._tick_interval_steps == 0
            and door_open
        ):
            return (ACTION_TICK, action_info)

        my_zone = self._my_zone(observation)
        if my_zone is None:
            return (ACTION_NOOP, action_info)

        for dev_idx, dev_id in enumerate(self._device_ids):
            if not _queue_has_head(observation, dev_idx):
                continue
            dev_zone = self._device_zone.get(dev_id)
            if dev_zone and my_zone == dev_zone:
                return (
                    ACTION_START_RUN,
                    {"device_id": dev_id},
                )

        goal_zone = self._goal_zone(observation)
        if goal_zone == my_zone:
            return (ACTION_NOOP, action_info)

        next_zone = _bfs_one_step(my_zone, goal_zone, self._adjacency)
        if next_zone is None:
            return (ACTION_NOOP, action_info)

        if next_zone == self._restricted_zone_id:
            if restricted_frozen or token_restricted <= 0:
                return (ACTION_NOOP, action_info)
            door_from_zone = "Z_SRA_RECEPTION"
            if my_zone != door_from_zone:
                next_zone = _bfs_one_step(
                    my_zone, door_from_zone, self._adjacency
                )
                if next_zone is not None:
                    return (ACTION_MOVE, {"to_zone": next_zone})
                return (ACTION_NOOP, action_info)
            if not door_open:
                return (
                    ACTION_OPEN_DOOR,
                    {"door_id": self._restricted_door_id},
                )
            return (ACTION_MOVE, {"to_zone": next_zone})

        return (ACTION_MOVE, {"to_zone": next_zone})

    def _goal_zone(self, observation: Dict[str, Any]) -> str:
        """Pick goal zone: first device with queue head, else default reception area."""
        for dev_id in self._device_ids:
            try:
                idx = self._device_ids.index(dev_id)
            except ValueError:
                continue
            if _queue_has_head(observation, idx):
                z = self._device_zone.get(dev_id)
                if z:
                    return z
        return "Z_SORTING_LANES"
