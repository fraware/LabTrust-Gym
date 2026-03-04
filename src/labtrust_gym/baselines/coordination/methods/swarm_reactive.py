"""
Swarm reactive: purely local rules with optional stability controls.

- If near restricted door and alarm -> close/exit (TICK or MOVE away).
- If device queue empty and specimens waiting -> QUEUE_RUN (when colocated).
- If qc_fail -> rerun path (local heuristic).
- Stability (scale_config): inertia_weight dampens direction change (prefer not
  reversing); congestion_penalty_scale reduces pile-ups by penalizing crowded zones.
Deterministic given obs and seed. Fallback: when over budget, same local rules
without stability terms.

Envelope (SOTA audit)
--------------------
steps: N/A; horizon-driven.
llm_calls_per_step: 0.
fallback: same local rules without stability terms when over budget.
max_latency_ms: bounded (local rules only).
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.coordination.interface import (
    ACTION_MOVE,
    ACTION_NOOP,
    ACTION_QUEUE_RUN,
    ACTION_START_RUN,
    ACTION_TICK,
    CoordinationMethod,
)
from labtrust_gym.baselines.coordination.methods.swarm_stability import (
    congestion_penalty,
    inertia_term,
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
    adjacency: set[tuple[str, str]],
) -> str | None:
    """Next zone from start toward goal. Deterministic."""
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


class SwarmReactive(CoordinationMethod):
    """Purely local rules with optional stability (inertia, congestion penalty)."""

    def __init__(self) -> None:
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._restricted_zone_id: str = "Z_RESTRICTED_BIOHAZARD"
        self._inertia_weight: float = 0.3
        self._congestion_scale: float = 0.5
        self._last_move: dict[str, tuple[str, str]] = {}

    @property
    def method_id(self) -> str:
        return "swarm_reactive"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(policy)
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
        sc = scale_config or {}
        self._inertia_weight = max(0.0, min(1.0, float(sc.get("inertia_weight", 0.3))))
        self._congestion_scale = max(0.0, float(sc.get("congestion_penalty_scale", 0.5)))
        self._last_move = {}

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agents}

        if not self._zone_ids and agents:
            sample = obs.get(agents[0]) or {}
            self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids({}, obs_sample=sample)
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

            if door_restricted_open(o) and my_zone == self._restricted_zone_id and t > 0 and t % 3 == 0:
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
                    q_len = int(qbd[idx].get("queue_len") or 0)
                if q_len > 0 and not queue_has_head(o, idx):
                    out[agent_id] = {
                        "action_index": ACTION_QUEUE_RUN,
                        "action_type": "QUEUE_RUN",
                        "args": {"device_id": dev_id},
                    }
                    break
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue

            # 4) Move toward first zone with work; apply inertia and congestion if enabled
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
                next_z: str | None = None
                neighbors = sorted([b for (a, b) in self._adjacency if a == my_zone])
                if neighbors and (self._congestion_scale > 0 or self._inertia_weight > 0):
                    zone_agent_count: dict[str, int] = {}
                    for aid in agents:
                        z = (
                            get_zone_from_obs(obs.get(aid) or {}, self._zone_ids)
                            or (obs.get(aid) or {}).get("zone_id")
                            or ""
                        )
                        zone_agent_count[z] = zone_agent_count.get(z, 0) + 1
                    last = self._last_move.get(agent_id)
                    best_score: float = -1e9
                    for n in neighbors:
                        pen = congestion_penalty(zone_agent_count.get(n, 0), self._congestion_scale)
                        current_dir = (1.0, 0.0) if (last and n != last[0]) else (0.0, 0.0)
                        damped = inertia_term(current_dir, self._inertia_weight)
                        inertia_bonus = damped[0]
                        score = -pen + inertia_bonus
                        if score > best_score:
                            best_score = score
                            next_z = n
                if next_z is None:
                    next_z = _bfs_one_step(my_zone, goal, self._adjacency)
                if next_z:
                    out[agent_id] = {
                        "action_index": ACTION_MOVE,
                        "action_type": "MOVE",
                        "args": {"from_zone": my_zone, "to_zone": next_z},
                    }
                    self._last_move[agent_id] = (my_zone, next_z)
        return out
