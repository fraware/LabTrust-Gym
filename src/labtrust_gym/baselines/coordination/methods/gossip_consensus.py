"""
Gossip consensus: local load balancing; agents share queue_head and load;
converge to stable assignment in fixed K gossip rounds per step.
Degrades gracefully under message loss (drop modeled deterministically).

CRDT usage for merge-order independence: zone load counts per round are merged via
pn_counter_merge (PN-counter) from crdt_merges; per-zone counts are max-aggregated
so merge(A then B) == merge(B then A) for zone_counts.

Envelope (SOTA audit)
--------------------
steps: N/A; horizon-driven.
llm_calls_per_step: 0.
fallback: drop message / prior view (graceful degradation).
max_latency_ms: bounded (K gossip rounds per step).
"""

from __future__ import annotations

import random
from typing import Any

from labtrust_gym.baselines.coordination.crdt_merges import pn_counter_merge
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

GOSSIP_ROUNDS = 3

# Aggregation mode for load from peers: "sum" (default), "median", "trim_mean".
# median/trim_mean reduce impact of Byzantine or faulty reports.
GOSSIP_AGGREGATION_DEFAULT = "sum"


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


def _message_lost(agent_i: int, agent_j: int, t: int, round_k: int, seed: int) -> bool:
    """Deterministic message loss: drop ~10% of messages at scale."""
    rng = random.Random(seed + t * 1000 + round_k * 100 + agent_i + agent_j)
    return rng.random() < 0.1


def _aggregate_load_values(values: list[int], mode: str) -> int:
    """Aggregate load values from self + peers. mode: sum, median, trim_mean."""
    if not values:
        return 0
    if mode == "sum":
        return sum(values)
    if mode == "median":
        sorted_v = sorted(values)
        n = len(sorted_v)
        return sorted_v[n // 2] if n else 0
    if mode == "trim_mean":
        if len(values) <= 2:
            return sum(values) // len(values) if values else 0
        sorted_v = sorted(values)
        trimmed = sorted_v[1:-1]
        return sum(trimmed) // len(trimmed)
    return sum(values)


class GossipConsensus(CoordinationMethod):
    """Agents gossip load/queue state; K rounds per step; assignment by consensus."""

    def __init__(self, gossip_rounds: int = GOSSIP_ROUNDS) -> None:
        self._gossip_rounds = gossip_rounds
        self._aggregation_mode = GOSSIP_AGGREGATION_DEFAULT
        self._rng: random.Random | None = None
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._seed = 0

    @property
    def method_id(self) -> str:
        return "gossip_consensus"

    def reset(self, seed: int, policy: dict[str, Any], scale_config: dict[str, Any]) -> None:
        self._rng = random.Random(seed)
        self._seed = seed
        if isinstance(scale_config, dict):
            self._gossip_rounds = int(scale_config.get("gossip_rounds", self._gossip_rounds))
            self._gossip_rounds = max(1, min(self._gossip_rounds, 20))
            agg = scale_config.get("gossip_aggregation") or scale_config.get("byzantine_mode")
            if agg in ("sum", "median", "trim_mean"):
                self._aggregation_mode = agg
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(policy)
        layout = (policy or {}).get("zone_layout") or {}
        if isinstance(layout, dict):
            self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        else:
            self._adjacency = set()

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

        # Build work items (device_id, work_id, zone_id) from any agent's obs
        worklist: list[tuple[str, str, str]] = []
        for agent_id in agents:
            o = obs.get(agent_id) or {}
            qbd = get_queue_by_device(o)
            for idx, dev_id in enumerate(self._device_ids):
                if not queue_has_head(o, idx):
                    continue
                dev_zone = self._device_zone.get(dev_id, "")
                head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
                worklist.append((dev_id, head or "W", dev_zone))
        worklist = list(dict.fromkeys([(a, b, c) for a, b, c in worklist]))

        # Local load: agent_id -> (zone_id, num_assigned)
        load: dict[str, tuple[str, int]] = {}
        for i, aid in enumerate(agents):
            o = obs.get(aid) or {}
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            load[aid] = (my_zone, 0)

        # Gossip rounds: share load; CRDT (PN-counter) merge for order independence when mode is sum
        for round_k in range(self._gossip_rounds):
            next_load: dict[str, tuple[str, int]] = {}
            for i, aid in enumerate(agents):
                z_i, n_i = load.get(aid, ("", 0))
                zone_counts: dict[str, int] = {z_i: n_i}
                collected = [n_i]
                for j, oid in enumerate(agents):
                    if i == j:
                        continue
                    if _message_lost(i, j, t, round_k, self._seed):
                        continue
                    z_j, n_j = load.get(oid, ("", 0))
                    zone_counts = pn_counter_merge(zone_counts, {z_j: n_j})
                    if z_i == z_j:
                        collected.append(n_j)
                n_new = (
                    zone_counts.get(z_i, 0)
                    if self._aggregation_mode == "sum"
                    else _aggregate_load_values(collected, self._aggregation_mode)
                )
                next_load[aid] = (z_i, n_new)
            load = next_load

        # Assign work to least-loaded colocated agent (consensus: same zone)
        used_work: set[tuple[str, str]] = set()
        for device_id, work_id, zone_id in worklist:
            if (device_id, work_id) in used_work:
                continue

            def _zone_of(aid: str) -> str:
                o = obs.get(aid) or {}
                return get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""

            candidates = [
                (aid, load.get(aid, ("", 0))[1])
                for aid in agents
                if not (obs.get(aid) or {}).get("log_frozen") and _zone_of(aid) == zone_id
            ]
            candidates.sort(key=lambda x: (x[1], x[0]))
            for aid, _ in candidates:
                if out[aid].get("action_index") != ACTION_NOOP:
                    continue
                used_work.add((device_id, work_id))
                out[aid] = {
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
                next_z = _bfs_one_step(my_zone, goal, self._adjacency)
                if next_z:
                    out[agent_id] = {
                        "action_index": ACTION_MOVE,
                        "action_type": "MOVE",
                        "args": {
                            "from_zone": my_zone,
                            "to_zone": next_z,
                        },
                    }
        return out
