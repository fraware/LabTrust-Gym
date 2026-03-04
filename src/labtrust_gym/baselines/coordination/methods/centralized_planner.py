"""
Centralized planner: single global worklist, greedy assignment.

Prioritizes STAT > URGENT > ROUTINE; respects colocation; prefers shortest queue.
Compute budget knob limits assignments per step to simulate planner saturation.
When over budget, worklist processing is truncated (remaining agents get NOOP);
no crash. Deterministic given seed and obs.

Compute envelope: O(agents * devices) per step for worklist build; assignment loop
capped by compute_budget (max assignments per step). Optional timeout via
scale_config["compute_budget_ms"] is not enforced in-process; use external
timeout for hard real-time. Fallback: over budget truncates assignments only.

Envelope (SOTA audit): Scale limits agents x devices; compute_budget caps assignments
per step; fallback truncates worklist (no crash). Latency bounded by worklist build
and BFS; no LLM calls.
"""

from __future__ import annotations

import random
from collections import deque
from typing import Any

from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_START_RUN,
    ACTION_TICK,
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
    adjacency: set[tuple[str, str]],
) -> str | None:
    """Next zone from start toward goal. Deterministic."""
    if start == goal:
        return None
    seen: set[str] = {start}
    queue: deque[tuple[str, list[str]]] = deque([(start, [])])
    while queue:
        node, path = queue.popleft()
        neighbors = sorted([b for (a, b) in adjacency if a == node and b not in seen])
        for n in neighbors:
            seen.add(n)
            new_path = path + [n]
            if n == goal:
                return new_path[0]
            queue.append((n, new_path))
    return None


class CentralizedPlanner(CoordinationMethod):
    """Single global planner: worklist, greedy assign by priority and colocation."""

    def __init__(self, compute_budget: int | None = None) -> None:
        self._compute_budget = compute_budget  # max assignments per step; None = no limit
        self._rng: random.Random | None = None
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._pz_to_engine: dict[str, str] = {}
        self._allowed_by_agent: dict[str, list[str]] = {}
        self._scale_config: dict[str, Any] = {}

    @property
    def method_id(self) -> str:
        return "centralized_planner"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._rng = random.Random(seed)
        self._scale_config = dict(scale_config or {})
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(policy)
        layout = (policy or {}).get("zone_layout") or {}
        self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        self._pz_to_engine = (policy or {}).get("pz_to_engine") or {}
        self._allowed_by_agent = {}
        try:
            from labtrust_gym.engine.rbac import get_allowed_actions

            for aid in self._pz_to_engine:
                allowed = get_allowed_actions(aid, policy)
                if allowed:
                    self._allowed_by_agent[aid] = list(allowed)
        except ImportError:
            pass

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agents}

        if not self._device_ids or not self._zone_ids:
            sample = obs.get(agents[0]) if agents else {}
            self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids({}, obs_sample=sample)
        if not self._device_ids:
            return out

        budget = self._compute_budget
        if budget is None:
            sc = self._scale_config
            if isinstance(sc.get("compute_budget_node_expansions"), (int, float)):
                budget = max(1, int(sc["compute_budget_node_expansions"]))
            else:
                budget = len(agents) * 2

        worklist: list[tuple[int, str, str, str]] = []  # (prio, device_id, work_id, zone_id)
        for agent_id in agents:
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            qbd = get_queue_by_device(o)
            for idx, dev_id in enumerate(self._device_ids):
                if not queue_has_head(o, idx):
                    continue
                dev_zone = self._device_zone.get(dev_id, "")
                if my_zone != dev_zone:
                    continue
                head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
                prio = 2 if "STAT" in str(head).upper() else (1 if "URGENT" in str(head).upper() else 0)
                worklist.append((prio, dev_id, head or "W", dev_zone))
        worklist.sort(key=lambda x: (-x[0], x[1], x[2]))
        assigned: set[str] = set()
        used_work: set[tuple[str, str]] = set()

        for prio, device_id, work_id, zone_id in worklist:
            if len(assigned) >= budget:
                break
            if (device_id, work_id) in used_work:
                continue
            for agent_id in agents:
                if agent_id in assigned:
                    continue
                allowed = self._allowed_by_agent.get(agent_id)
                if allowed is not None and "START_RUN" not in allowed:
                    continue
                o = obs.get(agent_id) or {}
                my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
                if my_zone != zone_id:
                    continue
                assigned.add(agent_id)
                used_work.add((device_id, work_id))
                out[agent_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {"device_id": device_id, "work_id": work_id},
                }
                break

        for agent_id in agents:
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            goal = self._zone_ids[0] if self._zone_ids else "Z_SORTING_LANES"
            for dev_id in self._device_ids:
                z = self._device_zone.get(dev_id)
                if not z:
                    continue
                qbd = get_queue_by_device(o)
                for idx, d in enumerate(self._device_ids):
                    if d != dev_id:
                        continue
                    if idx < len(qbd) and (qbd[idx].get("queue_len") or 0) > 0:
                        goal = z
                        break
            if my_zone == goal:
                continue
            allowed = self._allowed_by_agent.get(agent_id)
            if allowed is not None and "MOVE" not in allowed:
                pass
            else:
                next_z = _bfs_one_step(my_zone, goal, self._adjacency)
                if next_z:
                    out[agent_id] = {
                        "action_index": ACTION_MOVE,
                        "action_type": "MOVE",
                        "args": {"from_zone": my_zone, "to_zone": next_z},
                    }

        door_open = False
        for agent_id in agents:
            o = obs.get(agent_id) or {}
            if o.get("door_restricted_open") is not None:
                if hasattr(o["door_restricted_open"], "item"):
                    door_open = bool(o["door_restricted_open"].item())
                else:
                    door_open = bool(o.get("door_restricted_open", 0))
                break
        if door_open and t > 0 and t % 3 == 0:
            for agent_id in agents:
                if out[agent_id].get("action_index") == ACTION_NOOP:
                    allowed = self._allowed_by_agent.get(agent_id)
                    if allowed is not None and "TICK" not in allowed:
                        continue
                    out[agent_id] = {"action_index": ACTION_TICK}
                    break
        return out
