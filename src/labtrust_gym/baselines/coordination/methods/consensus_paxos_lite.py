"""
Consensus Paxos-lite: agreement on a single global digest (e.g. queue heads)
for use by local policies; bounded rounds. Decentralized class; no central planner.

Leader-based proposal in round 1; all agents adopt the leader's digest. Local
policies then use the agreed digest to choose actions (which device has which head).
Deterministic given seed and obs.
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
)
from labtrust_gym.engine.zones import build_adjacency_set

MAX_ROUNDS_DEFAULT = 2


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


def _digest_from_obs(obs: dict[str, Any], device_ids: list[str]) -> dict[str, str]:
    """Build canonical digest: device_id -> queue_head from queue_by_device."""
    out: dict[str, str] = {}
    qbd = get_queue_by_device(obs)
    for i, dev_id in enumerate(device_ids):
        if i < len(qbd):
            head = (qbd[i].get("queue_head") or "").strip()
            if head:
                out[dev_id] = head
    return out


class ConsensusPaxosLite(CoordinationMethod):
    """
    Bounded-round consensus on a global digest (queue heads). Leader proposes;
    all agents use the agreed digest for local action selection.
    """

    def __init__(self, max_rounds: int = MAX_ROUNDS_DEFAULT) -> None:
        self._max_rounds = max(1, min(max_rounds, 5))
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()

    @property
    def method_id(self) -> str:
        return "consensus_paxos_lite"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(
            policy
        )
        layout = (policy or {}).get("zone_layout") or {}
        if isinstance(layout, dict):
            self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        else:
            self._adjacency = set()
        if isinstance(scale_config, dict) and "consensus_max_rounds" in scale_config:
            self._max_rounds = max(
                1,
                min(int(scale_config.get("consensus_max_rounds", self._max_rounds)), 10),
            )

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
        if not self._device_ids or not self._zone_ids:
            return out

        # Bounded rounds: leader = agent at index (t % n); leader's view is the digest.
        leader_idx = t % max(1, len(agents))
        leader_id = agents[leader_idx]
        leader_obs = obs.get(leader_id) or {}
        agreed_digest = _digest_from_obs(leader_obs, self._device_ids)

        for agent_id in agents:
            o = obs.get(agent_id) or {}
            if log_frozen(o):
                continue
            my_zone = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            if not my_zone:
                continue

            qbd = get_queue_by_device(o)
            # Use agreed digest: device D has head agreed_digest.get(D)
            for idx, dev_id in enumerate(self._device_ids):
                head = agreed_digest.get(dev_id)
                if not head:
                    continue
                dev_zone = self._device_zone.get(dev_id, "")
                if my_zone != dev_zone:
                    continue
                if not device_qc_pass(o, idx):
                    continue
                # Colocated with device that has this head in digest -> START_RUN
                if queue_has_head(o, idx):
                    out[agent_id] = {
                        "action_index": ACTION_START_RUN,
                        "action_type": "START_RUN",
                        "args": {"device_id": dev_id, "work_id": head},
                    }
                    break
            if out[agent_id].get("action_index") != ACTION_NOOP:
                continue

            # Else move toward a device that has work in the digest
            goal_zone = my_zone
            for dev_id, head in agreed_digest.items():
                z = self._device_zone.get(dev_id)
                if z:
                    goal_zone = z
                    break
            if my_zone != goal_zone:
                next_z = _bfs_one_step(my_zone, goal_zone, self._adjacency)
                if next_z:
                    out[agent_id] = {
                        "action_index": ACTION_MOVE,
                        "action_type": "MOVE",
                        "args": {"from_zone": my_zone, "to_zone": next_z},
                    }
            else:
                # At goal zone; if queue has items but no head yet, QUEUE_RUN
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

        return out
