"""
Market / contract net: tasks announce; agents bid by estimated cost/time;
auctioneer selects winners. Optional collusion toggle for risk injection.
Deterministic given seed and obs.

RBAC: only START_RUN and MOVE are emitted when allowed by policy per agent.
Optional scale_config["forbidden_edges"]: set of (agent_id, (device_id, work_id))
to exclude (agent, task) pairs from winning (e.g. RBAC/token constraints).
Collusion: collusion=True lowers first agent's bid for injection studies; in
production use collusion=False. Bid caps and anomaly detector recommended when
INJ-COLLUSION-001, INJ-BID-SPOOF-001, INJ-COORD-BID-SHILL-001 are in scope.

Envelope (SOTA audit)
--------------------
steps: N/A; horizon-driven.
llm_calls_per_step: 0.
fallback: N/A (deterministic).
max_latency_ms: bounded (O(agents*devices) bid/select).
"""

from __future__ import annotations

import random
from typing import Any

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
    adjacency: set[tuple[str, str]],
) -> str | None:
    if start == goal:
        return None
    seen: set[str] = {start}
    queue: list[tuple[str, list[str]]] = [(start, [])]
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
    adjacency: set[tuple[str, str]],
    rng: random.Random,
) -> int:
    """Bid = path length estimate + small tie-break. Deterministic."""
    if agent_zone == task_zone:
        return 0
    seen: set[str] = {agent_zone}
    queue: list[tuple[str, int]] = [(agent_zone, 0)]
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
        self._rng: random.Random | None = None
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._allowed_by_agent: dict[str, list[str]] = {}
        self._forbidden_edges: set[tuple[Any, Any]] = set()

    @property
    def method_id(self) -> str:
        return "market_auction"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._rng = random.Random(seed)
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(policy)
        layout = (policy or {}).get("zone_layout") or {}
        if isinstance(layout, dict):
            self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        else:
            self._adjacency = set()
        self._allowed_by_agent = {}
        try:
            from labtrust_gym.engine.rbac import get_allowed_actions

            for aid in (policy or {}).get("pz_to_engine") or {}:
                allowed = get_allowed_actions(aid, policy)
                if allowed:
                    self._allowed_by_agent[aid] = list(allowed)
        except ImportError:
            pass
        fe = scale_config.get("forbidden_edges")
        if fe is not None and isinstance(fe, (set, list)):
            self._forbidden_edges = set(tuple(x) if isinstance(x, (list, tuple)) else (x,) for x in fe)
        else:
            self._forbidden_edges = set()

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agents}

        if not self._device_ids or not self._zone_ids:
            if agents:
                sample = obs.get(agents[0]) or {}
                self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids({}, obs_sample=sample)
        if not self._device_ids or not self._rng:
            return out

        # Announce tasks (work items with zone)
        tasks: list[tuple[str, str, str, int]] = []  # (device_id, work_id, zone_id, priority)
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
                prio = 2 if "STAT" in str(head).upper() else (1 if "URGENT" in str(head).upper() else 0)
                tasks.append((dev_id, head or "W", dev_zone, prio))
        tasks.sort(key=lambda x: (-x[3], x[0], x[1]))
        seen_task: set[tuple[str, str]] = set()

        # Bids: (agent_id, cost, device_id, work_id, zone_id)
        for device_id, work_id, zone_id, _ in tasks:
            if (device_id, work_id) in seen_task:
                continue
            seen_task.add((device_id, work_id))
            bids: list[tuple[str, int, str, str, str]] = []
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
            dev_id, work_id = bids[0][2], bids[0][3]
            forbidden = (winner_id, (dev_id, work_id)) in self._forbidden_edges
            allowed = self._allowed_by_agent.get(winner_id)
            can_start = (not allowed or "START_RUN" in allowed) and not forbidden
            if can_start and out[winner_id].get("action_index") == ACTION_NOOP:
                out[winner_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {"device_id": dev_id, "work_id": work_id},
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
                    if d == dev_id and i < len(qbd) and (qbd[i].get("queue_len") or 0) > 0:
                        goal = z
                        break
            if my_zone != goal:
                allowed = self._allowed_by_agent.get(agent_id)
                if allowed and "MOVE" not in allowed:
                    continue
                next_z = _bfs_one_step(my_zone, goal, self._adjacency)
                if next_z:
                    out[agent_id] = {
                        "action_index": ACTION_MOVE,
                        "action_type": "MOVE",
                        "args": {"from_zone": my_zone, "to_zone": next_z},
                    }
        return out

    def combine_submissions(
        self,
        submissions: dict[str, dict[str, Any]],
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        """
        Combine per-agent bid submissions into joint action. Each submission may
        contain "bid" with cost, device_id, work_id, zone_id; or flat cost/device_id/work_id/zone_id.
        Runs same winner selection and MOVE logic as propose_actions.
        """
        agents = sorted(obs.keys()) if obs else sorted(submissions.keys())
        out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agents}

        if not self._device_ids or not self._zone_ids:
            if agents and obs:
                sample = obs.get(agents[0]) or {}
                self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids({}, obs_sample=sample)
        if not self._device_ids or not self._rng:
            return out

        # Build tasks from obs (same as propose_actions)
        tasks: list[tuple[str, str, str, int]] = []
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
                prio = 2 if "STAT" in str(head).upper() else (1 if "URGENT" in str(head).upper() else 0)
                tasks.append((dev_id, head or "W", dev_zone, prio))
        tasks.sort(key=lambda x: (-x[3], x[0], x[1]))
        seen_task: set[tuple[str, str]] = set()

        # Bids from submissions: (agent_id, cost, device_id, work_id, zone_id)
        for device_id, work_id, zone_id, _ in tasks:
            if (device_id, work_id) in seen_task:
                continue
            seen_task.add((device_id, work_id))
            bids_list: list[tuple[str, int, str, str, str]] = []
            for agent_id in agents:
                sub = submissions.get(agent_id) or {}
                bid = sub.get("bid") if isinstance(sub.get("bid"), dict) else sub
                if not isinstance(bid, dict):
                    continue
                cost_val = bid.get("cost")
                if cost_val is None:
                    continue
                try:
                    cost = int(cost_val)
                except (TypeError, ValueError):
                    continue
                dev = bid.get("device_id") or bid.get("device")
                work = bid.get("work_id") or bid.get("work")
                z = bid.get("zone_id") or bid.get("zone")
                if (dev or "") != device_id or (work or "") != work_id or (z or "") != zone_id:
                    continue
                if log_frozen(obs.get(agent_id) or {}):
                    continue
                bids_list.append((agent_id, cost, device_id, work_id, zone_id))
            if not bids_list:
                continue
            bids_list.sort(key=lambda x: (x[1], x[0]))
            winner_id = bids_list[0][0]
            dev_id, work_id = bids_list[0][2], bids_list[0][3]
            forbidden = (winner_id, (dev_id, work_id)) in self._forbidden_edges
            allowed = self._allowed_by_agent.get(winner_id)
            can_start = (not allowed or "START_RUN" in allowed) and not forbidden
            if can_start and out[winner_id].get("action_index") == ACTION_NOOP:
                out[winner_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {"device_id": dev_id, "work_id": work_id},
                }

        # Move toward zone with work (same as propose_actions)
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
                    if d == dev_id and i < len(qbd) and (qbd[i].get("queue_len") or 0) > 0:
                        goal = z
                        break
            if my_zone != goal:
                allowed = self._allowed_by_agent.get(agent_id)
                if allowed and "MOVE" not in allowed:
                    continue
                next_z = _bfs_one_step(my_zone, goal, self._adjacency)
                if next_z:
                    out[agent_id] = {
                        "action_index": ACTION_MOVE,
                        "action_type": "MOVE",
                        "args": {"from_zone": my_zone, "to_zone": next_z},
                    }
        return out
