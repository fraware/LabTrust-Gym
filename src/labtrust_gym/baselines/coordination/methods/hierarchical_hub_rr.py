"""
Hierarchical hub with rapid response: hub assigns to cells; local RR handles exceptions.
Message delay between hub and cells modeled deterministically from scale.

Handoff contract: hub assigns (agent_id -> device_id, work_id, zone_id) and records
assignment_step; cells execute START_RUN/MOVE locally. Region partition: zones/cells
are derived from policy zone_layout (graph_edges, zones); each cell corresponds to
a zone or site. When policy has zone_layout with graph_edges, adjacency is used for
local BFS move; message_delay_steps(num_agents, num_sites, t, seed) models hub-cell latency.
"""

from __future__ import annotations

import random
from typing import Any

from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
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


def _bfs_one_step(start: str, goal: str, adjacency: set[tuple[str, str]]) -> str | None:
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


def _message_delay_steps(num_agents: int, num_sites: int, t: int, seed: int) -> int:
    rng = random.Random(seed + t)
    base = min(2, 1 + (num_agents // 10) + max(0, num_sites - 1))
    return base + rng.randint(0, 1)


class HierarchicalHubRR(CoordinationMethod):
    """Hub assigns work to cells; cells handle local exceptions; message delay by scale."""

    def __init__(self, message_delay_scale: float = 1.0) -> None:
        self._message_delay_scale = message_delay_scale
        self._rng: random.Random | None = None
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._seed = 0
        self._num_agents = 0
        self._num_sites = 1
        self._hub_assignments: dict[str, tuple[str, str, str]] = {}
        self._assignment_step: dict[str, int] = {}
        self._scale_config: dict[str, Any] = {}

    @property
    def method_id(self) -> str:
        return "hierarchical_hub_rr"

    def reset(self, seed: int, policy: dict[str, Any], scale_config: dict[str, Any]) -> None:
        self._rng = random.Random(seed)
        self._seed = seed
        self._scale_config = dict(scale_config or {})
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(policy)
        layout = (policy or {}).get("zone_layout") or {}
        if isinstance(layout, dict):
            self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        else:
            self._adjacency = set()
        self._num_agents = int((scale_config or {}).get("num_agents_total", 10))
        self._num_sites = int((scale_config or {}).get("num_sites", 1))
        self._hub_assignments = {}
        self._assignment_step = {}

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
        if not self._device_ids:
            return out
        delay = _message_delay_steps(self._num_agents, self._num_sites, t, self._seed)
        used_work: set[tuple[str, str]] = set()

        for agent_id in agents:
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            if restricted_zone_frozen(o) and door_restricted_open(o):
                if t > 0 and t % 3 == 0:
                    out[agent_id] = {"action_index": ACTION_TICK}
                continue
            qbd = get_queue_by_device(o)
            for idx, dev_id in enumerate(self._device_ids):
                if not queue_has_head(o, idx) or not device_qc_pass(o, idx):
                    continue
                dev_zone = self._device_zone.get(dev_id, "")
                if my_zone != dev_zone:
                    continue
                head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
                if (dev_id, head) in used_work:
                    continue
                used_work.add((dev_id, head))
                out[agent_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {"device_id": dev_id, "work_id": head},
                }
                break

        for agent_id in agents:
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue
            assign = self._hub_assignments.get(agent_id)
            step_assign = self._assignment_step.get(agent_id, -1)
            if assign is None or step_assign < 0 or t - step_assign < delay:
                continue
            device_id, work_id, zone_id = assign
            o = obs.get(agent_id) or {}
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            if my_zone == zone_id and (device_id, work_id) not in used_work:
                out[agent_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {"device_id": device_id, "work_id": work_id},
                }
                used_work.add((device_id, work_id))
                del self._hub_assignments[agent_id]
                del self._assignment_step[agent_id]

        worklist: list[tuple[int, str, str, str]] = []
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

        for prio, device_id, work_id, zone_id in worklist:
            if (device_id, work_id) in used_work:
                continue
            for agent_id in agents:
                if agent_id in self._hub_assignments:
                    continue
                o = obs.get(agent_id) or {}
                my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
                if my_zone == zone_id:
                    self._hub_assignments[agent_id] = (
                        device_id,
                        work_id,
                        zone_id,
                    )
                    self._assignment_step[agent_id] = t
                    used_work.add((device_id, work_id))
                    break

        for agent_id in agents:
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            goal = self._zone_ids[0] if self._zone_ids else my_zone
            assign = self._hub_assignments.get(agent_id)
            if assign:
                _, _, zone_id = assign
                goal = zone_id
            else:
                qbd = get_queue_by_device(o)
                for dev_id in self._device_ids:
                    z = self._device_zone.get(dev_id)
                    if not z:
                        continue
                    for i, d in enumerate(self._device_ids):
                        if d == dev_id and i < len(qbd):
                            if (qbd[i].get("queue_len") or 0) > 0:
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
        trace_path = self._scale_config.get("trace_path")
        if trace_path is not None:
            try:
                from pathlib import Path
                from labtrust_gym.baselines.coordination.trace import (
                    append_trace_event,
                    trace_from_contract_record,
                )
                path = Path(trace_path) if isinstance(trace_path, str) else trace_path
                event = trace_from_contract_record(self.method_id, t, out)
                append_trace_event(path, event)
            except Exception:
                pass
        return out
