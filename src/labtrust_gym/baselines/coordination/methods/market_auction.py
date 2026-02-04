"""
Market / contract net: tasks announce; agents bid by estimated cost/time;
auctioneer selects winners. Optional collusion toggle for risk injection.
Deterministic given seed and obs.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Set, Tuple

from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_START_RUN,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.obs_utils import (
    extract_zone_and_device_ids,
    get_queue_by_device,
    get_zone_from_obs,
    log_frozen,
    queue_has_head,
)
from labtrust_gym.engine.zones import build_adjacency_set


def _bfs_one_step(
    start: str,
    goal: str,
    adjacency: Set[Tuple[str, str]],
) -> Optional[str]:
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


def _estimate_cost(
    agent_zone: str,
    task_zone: str,
    adjacency: Set[Tuple[str, str]],
    rng: random.Random,
) -> int:
    """Bid = path length estimate + small tie-break. Deterministic."""
    if agent_zone == task_zone:
        return 0
    seen: Set[str] = {agent_zone}
    queue: List[Tuple[str, int]] = [(agent_zone, 0)]
    while queue:
        node, dist = queue.pop(0)
        for a, b in adjacency:
            if a != node or b in seen:
                continue
            seen.add(b)
            if b == task_zone:
                return dist + 1 + rng.randint(0, 1)
            queue.append((b, dist + 1))
    return 999 + rng.randint(0, 10)


class MarketAuction(CoordinationMethod):
    """Contract net: tasks announced, agents bid, auctioneer selects lowest bid."""

    def __init__(self, collusion: bool = False) -> None:
        self._collusion = collusion
        self._rng: Optional[random.Random] = None
        self._zone_ids: List[str] = []
        self._device_ids: List[str] = []
        self._device_zone: Dict[str, str] = {}
        self._adjacency: Set[Tuple[str, str]] = set()

    @property
    def method_id(self) -> str:
        return "market_auction"

    def reset(
        self,
        seed: int,
        policy: Dict[str, Any],
        scale_config: Dict[str, Any],
    ) -> None:
        self._rng = random.Random(seed)
        self._zone_ids, self._device_ids, self._device_zone = (
            extract_zone_and_device_ids(policy)
        )
        layout = (policy or {}).get("zone_layout") or {}
        if isinstance(layout, dict):
            self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        else:
            self._adjacency = set()

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

        if not self._device_ids or not self._zone_ids:
            if agents:
                sample = obs.get(agents[0]) or {}
                self._zone_ids, self._device_ids, self._device_zone = (
                    extract_zone_and_device_ids({}, obs_sample=sample)
                )
        if not self._device_ids or not self._rng:
            return out

        # Announce tasks (work items with zone)
        tasks: List[Tuple[str, str, str, int]] = (
            []
        )  # (device_id, work_id, zone_id, priority)
        for agent_id in agents:
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            qbd = get_queue_by_device(o)
            for idx, dev_id in enumerate(self._device_ids):
                if not queue_has_head(o, idx):
                    continue
                dev_zone = self._device_zone.get(dev_id, "")
                head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
                prio = (
                    2
                    if "STAT" in str(head).upper()
                    else (1 if "URGENT" in str(head).upper() else 0)
                )
                tasks.append((dev_id, head or "W", dev_zone, prio))
        tasks.sort(key=lambda x: (-x[3], x[0], x[1]))
        seen_task: Set[Tuple[str, str]] = set()

        # Bids: (agent_id, cost, device_id, work_id, zone_id)
        for device_id, work_id, zone_id, _ in tasks:
            if (device_id, work_id) in seen_task:
                continue
            seen_task.add((device_id, work_id))
            bids: List[Tuple[str, int, str, str, str]] = []
            for agent_id in agents:
                o = obs.get(agent_id) or {}
                if log_frozen(o):
                    continue
                my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
                if my_zone != zone_id:
                    continue
                cost = _estimate_cost(my_zone, zone_id, self._adjacency, self._rng)
                if self._collusion and agent_id == agents[0]:
                    cost = max(0, cost - 5)
                bids.append((agent_id, cost, device_id, work_id, zone_id))
            if not bids:
                continue
            bids.sort(key=lambda x: (x[1], x[0]))
            winner_id = bids[0][0]
            if out[winner_id].get("action_index") == ACTION_NOOP:
                out[winner_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {"device_id": bids[0][2], "work_id": bids[0][3]},
                }

        # Move toward zone with work
        for agent_id in agents:
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            goal = self._zone_ids[0] if self._zone_ids else my_zone
            qbd = get_queue_by_device(o)
            for dev_id in self._device_ids:
                z = self._device_zone.get(dev_id)
                if not z:
                    continue
                for i, d in enumerate(self._device_ids):
                    if (
                        d == dev_id
                        and i < len(qbd)
                        and (qbd[i].get("queue_len") or 0) > 0
                    ):
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
