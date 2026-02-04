"""
Swarm reactive: purely local rules, zero global state.

- If near restricted door and alarm -> close/exit (TICK or MOVE away).
- If device queue empty and specimens waiting -> QUEUE_RUN (when colocated).
- If qc_fail -> rerun path (local heuristic).
Deterministic given obs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_QUEUE_RUN,
    ACTION_START_RUN,
    ACTION_TICK,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.obs_utils import (
    device_qc_pass,
    door_restricted_open,
    extract_zone_and_device_ids,
    get_queue_by_device,
    get_zone_from_obs,
    log_frozen,
    queue_has_head,
    restricted_zone_frozen,
)
from labtrust_gym.engine.zones import build_adjacency_set


def _bfs_one_step(
    start: str,
    goal: str,
    adjacency: Set[Tuple[str, str]],
) -> Optional[str]:
    """Next zone from start toward goal. Deterministic."""
    if start == goal:
        return None
    seen: Set[str] = {start}
    queue: List[Tuple[str, List[str]]] = [(start, [])]
    while queue:
        node, path = queue.pop(0)
        neighbors = sorted([b for (a, b) in adjacency if a == node and b not in seen])
        for n in neighbors:
            seen.add(n)
            new_path = path + [n]
            if n == goal:
                return new_path[0]
            queue.append((n, new_path))
    return None


class SwarmReactive(CoordinationMethod):
    """Purely local rules; no global state or messaging."""

    def __init__(self) -> None:
        self._zone_ids: List[str] = []
        self._device_ids: List[str] = []
        self._device_zone: Dict[str, str] = {}
        self._adjacency: Set[Tuple[str, str]] = set()
        self._restricted_zone_id: str = "Z_RESTRICTED_BIOHAZARD"

    @property
    def method_id(self) -> str:
        return "swarm_reactive"

    def reset(
        self,
        seed: int,
        policy: Dict[str, Any],
        scale_config: Dict[str, Any],
    ) -> None:
        self._zone_ids, self._device_ids, self._device_zone = (
            extract_zone_and_device_ids(policy)
        )
        layout = (policy or {}).get("zone_layout") or {}
        if isinstance(layout, dict):
            self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        else:
            self._adjacency = set()
        zones_list = (policy or {}).get("zone_layout") or {}
        if isinstance(zones_list, dict):
            zones_list = zones_list.get("zones") or []
        for z in zones_list or []:
            zid = z.get("zone_id") if isinstance(z, dict) else None
            if zid and "RESTRICTED" in str(zid).upper():
                self._restricted_zone_id = str(zid)
                break

    def propose_actions(
        self,
        obs: Dict[str, Any],
        infos: Dict[str, Dict[str, Any]],
        t: int,
    ) -> Dict[str, Dict[str, Any]]:
        agents = sorted(obs.keys())
        out: Dict[str, Dict[str, Any]] = {
            a: {"action_index": ACTION_NOOP} for a in agents
        }

        if not self._zone_ids and agents:
            sample = obs.get(agents[0]) or {}
            self._zone_ids, self._device_ids, self._device_zone = (
                extract_zone_and_device_ids({}, obs_sample=sample)
            )
        if not self._zone_ids:
            return out

        for agent_id in agents:
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            if not my_zone:
                continue

            # 1) Near restricted door and alarm / frozen -> TICK or MOVE away
            if restricted_zone_frozen(o) and my_zone == self._restricted_zone_id:
                if door_restricted_open(o) and t > 0 and t % 3 == 0:
                    out[agent_id] = {"action_index": ACTION_TICK}
                else:
                    next_z = _bfs_one_step(
                        my_zone,
                        self._zone_ids[0] if self._zone_ids else my_zone,
                        self._adjacency,
                    )
                    if next_z:
                        out[agent_id] = {
                            "action_index": ACTION_MOVE,
                            "action_type": "MOVE",
                            "args": {"from_zone": my_zone, "to_zone": next_z},
                        }
                continue

            if (
                door_restricted_open(o)
                and my_zone == self._restricted_zone_id
                and t > 0
                and t % 3 == 0
            ):
                out[agent_id] = {"action_index": ACTION_TICK}
                continue

            # 2) Colocated with device that has queue head -> START_RUN (or QUEUE_RUN if ops role implied by obs)
            qbd = get_queue_by_device(o)
            for idx, dev_id in enumerate(self._device_ids):
                if not queue_has_head(o, idx):
                    continue
                dev_zone = self._device_zone.get(dev_id, "")
                if my_zone != dev_zone:
                    continue
                head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
                if not device_qc_pass(o, idx):
                    continue
                out[agent_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {"device_id": dev_id, "work_id": head},
                }
                break
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue

            # 3) Device queue has items but no head (specimens waiting) -> QUEUE_RUN if colocated
            for idx, dev_id in enumerate(self._device_ids):
                dev_zone = self._device_zone.get(dev_id, "")
                if my_zone != dev_zone:
                    continue
                q_len = 0
                if idx < len(qbd):
                    q_len = int((qbd[idx].get("queue_len") or 0))
                if q_len > 0 and not queue_has_head(o, idx):
                    out[agent_id] = {
                        "action_index": ACTION_QUEUE_RUN,
                        "action_type": "QUEUE_RUN",
                        "args": {"device_id": dev_id},
                    }
                    break
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue

            # 4) Move toward first zone with work
            goal = self._zone_ids[0] if self._zone_ids else my_zone
            for dev_id in self._device_ids:
                z = self._device_zone.get(dev_id)
                if not z:
                    continue
                for i, d in enumerate(self._device_ids):
                    if d != dev_id:
                        continue
                    if i < len(qbd) and (qbd[i].get("queue_len") or 0) > 0:
                        goal = z
                        break
            if my_zone != goal:
                next_z = _bfs_one_step(my_zone, goal, self._adjacency)
                if next_z:
                    out[agent_id] = {
                        "action_index": ACTION_MOVE,
                        "action_type": "MOVE",
                        "args": {"from_zone": my_zone, "to_zone": next_z},
                    }
        return out
