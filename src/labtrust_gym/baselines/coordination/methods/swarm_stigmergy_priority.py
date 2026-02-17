"""
Swarm stigmergy (priority-weighted): agents leave virtual pheromone by priority
class; others follow gradients. No central plan. Swarm class.

Pheromone is stored per zone; decay each step. When an agent performs QUEUE_RUN
or START_RUN, it deposits pheromone in its current zone (weighted by priority if
available). Agents move toward adjacent zones with higher pheromone when not
already doing work. Deterministic given seed and obs.
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
from labtrust_gym.baselines.coordination.obs_utils import (
    device_qc_pass,
    extract_zone_and_device_ids,
    get_queue_by_device,
    get_zone_from_obs,
    log_frozen,
    queue_has_head,
    restricted_zone_frozen,
)
from labtrust_gym.baselines.coordination.methods.swarm_stability import (
    congestion_penalty,
    pheromone_diffusion as _pheromone_diffusion_fn,
)
from labtrust_gym.engine.zones import build_adjacency_set

PHEROMONE_DECAY = 0.95
DEPOSIT_DEFAULT = 1.0
STAT_WEIGHT = 2.0
URGENT_WEIGHT = 1.5


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


class SwarmStigmergyPriority(CoordinationMethod):
    """
    Priority-weighted stigmergy: pheromone per zone; deposit on work actions;
    follow gradient toward higher pheromone. Stability knobs: inertia_weight,
    congestion_penalty_scale, pheromone_diffusion_decay (spread from neighbors).
    No central plan. Deterministic given seed and obs.
    """

    def __init__(
        self,
        decay: float = PHEROMONE_DECAY,
        deposit: float = DEPOSIT_DEFAULT,
    ) -> None:
        self._decay = max(0.0, min(1.0, decay))
        self._deposit = max(0.0, deposit)
        self._pheromone: dict[str, float] = {}
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._restricted_zone_id = "Z_RESTRICTED_BIOHAZARD"
        self._inertia_weight: float = 0.3
        self._congestion_scale: float = 0.5
        self._pheromone_diffusion_decay: float = 0.9
        self._last_move: dict[str, tuple[str, str]] = {}

    @property
    def method_id(self) -> str:
        return "swarm_stigmergy_priority"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._pheromone = {}
        self._last_move = {}
        sc = scale_config or {}
        self._inertia_weight = float(sc.get("inertia_weight", 0.3))
        self._congestion_scale = float(sc.get("congestion_penalty_scale", 0.5))
        self._pheromone_diffusion_decay = float(
            sc.get("pheromone_diffusion_decay", 0.9)
        )
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
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agents}

        if not self._zone_ids and agents:
            sample = obs.get(agents[0]) or {}
            self._zone_ids, self._device_ids, self._device_zone = (
                extract_zone_and_device_ids({}, obs_sample=sample)
            )
        if not self._zone_ids:
            return out

        # Decay pheromone
        for z in list(self._pheromone.keys()):
            self._pheromone[z] *= self._decay
            if self._pheromone[z] < 0.01:
                del self._pheromone[z]
        # Diffusion from neighbors (stability)
        if self._pheromone_diffusion_decay > 0 and self._adjacency:
            prev = dict(self._pheromone)
            for z in list(prev.keys()):
                neighbors = [b for (a, b) in self._adjacency if a == z]
                nvals = [prev.get(n, 0.0) for n in neighbors]
                if nvals:
                    diff = _pheromone_diffusion_fn(
                        nvals, decay=self._pheromone_diffusion_decay
                    )
                    self._pheromone[z] = self._pheromone.get(z, 0) + diff

        # First pass: decide work actions and deposit pheromone
        for agent_id in agents:
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            if not my_zone:
                continue

            if restricted_zone_frozen(o) and my_zone == self._restricted_zone_id:
                out[agent_id] = {"action_index": ACTION_TICK}
                continue

            qbd = get_queue_by_device(o)
            priority_weight = self._deposit
            for idx, dev_id in enumerate(self._device_ids):
                if not queue_has_head(o, idx):
                    continue
                dev_zone = self._device_zone.get(dev_id, "")
                if my_zone != dev_zone:
                    continue
                if not device_qc_pass(o, idx):
                    continue
                head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
                out[agent_id] = {
                    "action_index": ACTION_START_RUN,
                    "action_type": "START_RUN",
                    "args": {"device_id": dev_id, "work_id": head},
                }
                self._pheromone[my_zone] = self._pheromone.get(my_zone, 0) + priority_weight
                break
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue

            for idx, dev_id in enumerate(self._device_ids):
                dev_zone = self._device_zone.get(dev_id, "")
                if my_zone != dev_zone:
                    continue
                q_len = int((qbd[idx] if idx < len(qbd) else {}).get("queue_len") or 0)
                if q_len > 0 and not queue_has_head(o, idx):
                    out[agent_id] = {
                        "action_index": ACTION_QUEUE_RUN,
                        "action_type": "QUEUE_RUN",
                        "args": {"device_id": dev_id},
                    }
                    self._pheromone[my_zone] = self._pheromone.get(my_zone, 0) + self._deposit
                    break
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue

            # Follow gradient: move to adjacent zone with highest pheromone (minus congestion, plus inertia)
            zone_agent_count: dict[str, int] = {}
            for aid in agents:
                z = get_zone_from_obs(obs.get(aid) or {}, self._zone_ids) or (obs.get(aid) or {}).get("zone_id") or ""
                zone_agent_count[z] = zone_agent_count.get(z, 0) + 1
            my_pheromone = self._pheromone.get(my_zone, 0)
            last_from_zone = None
            if agent_id in self._last_move:
                last_from_zone = self._last_move[agent_id][0]
            best_next: str | None = None
            best_val = my_pheromone
            for (a, b) in self._adjacency:
                if a != my_zone:
                    continue
                val = self._pheromone.get(b, 0)
                penalty = congestion_penalty(
                    zone_agent_count.get(b, 0), scale=self._congestion_scale
                )
                inertia_bonus = (
                    self._inertia_weight if (last_from_zone is None or b != last_from_zone) else 0.0
                )
                score = val - penalty + inertia_bonus
                if score > best_val:
                    best_val = score
                    best_next = b
            if best_next:
                out[agent_id] = {
                    "action_index": ACTION_MOVE,
                    "action_type": "MOVE",
                    "args": {"from_zone": my_zone, "to_zone": best_next},
                }
                self._last_move[agent_id] = (my_zone, best_next)
            else:
                # No gradient; move toward first device zone with work
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
                        self._last_move[agent_id] = (my_zone, next_z)
        return out
