"""
Ripple Effect Protocol: local intent + signed broadcast to neighbors, conflict resolution
without a central planner. Uses SignedMessageBus; neighbor graph from zone topology
or scale config. Deterministic given seed and obs.

Envelope (SOTA audit)
--------------------
steps: N/A; horizon-driven.
llm_calls_per_step: 0.
fallback: N/A (deterministic).
max_latency_ms: bounded (signed bus + local reconcile).
"""

from __future__ import annotations

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
from labtrust_gym.coordination.bus import SignedMessageBus
from labtrust_gym.coordination.identity import (
    COORD_REPLAY_DETECTED,
    COORD_SIGNATURE_INVALID,
    KEY_MESSAGE_TYPE,
    KEY_PAYLOAD,
    KEY_SENDER_ID,
    build_key_store,
    sign_message,
    verify_message_find_signer,
)
from labtrust_gym.engine.zones import build_adjacency_set

MESSAGE_TYPE_RIPPLE_INTENT = "ripple_intent"


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


def _build_neighbor_graph(
    agents: list[str],
    agent_zone: dict[str, str],
    zone_adjacency: set[tuple[str, str]],
) -> dict[str, list[str]]:
    """
    Neighbor graph: agent j's neighbors = agents in same zone or in adjacent zones.
    Deterministic: sorted order.
    """
    zone_neighbors: dict[str, set[str]] = {}
    for (a, b) in zone_adjacency:
        zone_neighbors.setdefault(a, set()).add(b)
        zone_neighbors.setdefault(b, set()).add(a)
    out: dict[str, list[str]] = {}
    for j in agents:
        z_j = agent_zone.get(j) or ""
        allowed_zones = {z_j} | zone_neighbors.get(z_j, set())
        neighbors = [a for a in agents if a != j and (agent_zone.get(a) or "") in allowed_zones]
        out[j] = sorted(neighbors)
    return out


def _compute_local_intent(
    agent_id: str,
    obs: dict[str, Any],
    zone_ids: list[str],
    device_ids: list[str],
    device_zone: dict[str, str],
    t: int,
) -> dict[str, Any] | None:
    """
    One intent per agent: preferred (device_id, work_id, priority) if colocated and
    queue_has_head; else (zone_id for MOVE). Returns payload dict or None (NOOP).
    """
    o = obs.get(agent_id) or {}
    if log_frozen(o):
        return None
    my_zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
    qbd = get_queue_by_device(o)
    best_prio = -1
    best_device: str | None = None
    best_work: str | None = None
    for idx, dev_id in enumerate(device_ids):
        if not queue_has_head(o, idx):
            continue
        dev_zone = device_zone.get(dev_id, "")
        if my_zone != dev_zone:
            continue
        head = (qbd[idx] if idx < len(qbd) else {}).get("queue_head", "W")
        prio = 2 if "STAT" in str(head).upper() else (1 if "URGENT" in str(head).upper() else 0)
        if prio > best_prio:
            best_prio = prio
            best_device = dev_id
            best_work = head or "W"
    if best_device is not None:
        return {
            "agent_id": agent_id,
            "step": t,
            "zone_id": my_zone,
            "device_id": best_device,
            "priority": best_prio,
            "work_id": best_work or "W",
            "action_type": "START_RUN",
            "args": {"device_id": best_device, "work_id": best_work or "W"},
        }
    goal_zone = my_zone
    for idx, dev_id in enumerate(device_ids):
        if idx < len(qbd) and (qbd[idx].get("queue_len") or 0) > 0:
            z = device_zone.get(dev_id)
            if z:
                goal_zone = z
                break
    if goal_zone != my_zone:
        return {
            "agent_id": agent_id,
            "step": t,
            "zone_id": my_zone,
            "device_id": "",
            "priority": 0,
            "work_id": "",
            "action_type": "MOVE",
            "args": {"from_zone": my_zone, "to_zone": goal_zone},
        }
    return {
        "agent_id": agent_id,
        "step": t,
        "zone_id": my_zone,
        "device_id": "",
        "priority": 0,
        "work_id": "",
        "action_type": "NOOP",
        "args": {},
    }


def _resolve_conflicts(
    agent_id: str,
    own_intent: dict[str, Any] | None,
    neighbor_intents: list[tuple[str, dict[str, Any]]],
    device_zone: dict[str, str],
    zone_ids: list[str],
    adjacency: set[tuple[str, str]],
    my_zone: str,
) -> dict[str, Any]:
    """
    Own + neighbor intents; conflict: at most one agent per (device_id, work_id).
    Winner = highest priority, tie-break agent_id. This agent gets START_RUN only
    if they win their claimed (D, W); else MOVE if own intent was MOVE; else NOOP.
    """
    all_intents: list[tuple[str, dict[str, Any]]] = []
    if own_intent:
        all_intents.append((agent_id, own_intent))
    all_intents.extend(neighbor_intents)
    claims: dict[tuple[str, str], tuple[int, str]] = {}
    for sid, payload in all_intents:
        if not isinstance(payload, dict) or (payload.get("action_type") or "").strip() != "START_RUN":
            continue
        args = payload.get("args") or {}
        dev = args.get("device_id") or ""
        work = args.get("work_id") or ""
        if not dev:
            continue
        prio = int(payload.get("priority") or 0)
        key = (dev, work)
        if key not in claims or prio > claims[key][0] or (
            prio == claims[key][0] and sid < claims[key][1]
        ):
            claims[key] = (prio, sid)
    if own_intent and (own_intent.get("action_type") or "").strip() == "START_RUN":
        args = own_intent.get("args") or {}
        dev = args.get("device_id") or ""
        work = args.get("work_id") or ""
        if dev and (dev, work) in claims and claims[(dev, work)][1] == agent_id:
            return {"action_type": "START_RUN", "args": args}
    if own_intent and (own_intent.get("action_type") or "").strip() == "MOVE":
        args = own_intent.get("args") or {}
        to_zone = args.get("to_zone")
        if to_zone and my_zone != to_zone:
            next_z = _bfs_one_step(my_zone, to_zone, adjacency)
            if next_z:
                return {
                    "action_type": "MOVE",
                    "args": {"from_zone": my_zone, "to_zone": next_z},
                }
    return {"action_type": "NOOP", "args": {}}


def _intent_to_action_dict(
    resolved: dict[str, Any],
) -> dict[str, Any]:
    """Map resolved intent to runner action_dict (action_index, action_type, args)."""
    action_type = (resolved.get("action_type") or "NOOP").strip()
    args = resolved.get("args") or {}
    if action_type == "NOOP":
        return {"action_index": ACTION_NOOP}
    if action_type == "TICK":
        return {"action_index": ACTION_TICK}
    if action_type == "MOVE":
        return {
            "action_index": ACTION_MOVE,
            "action_type": "MOVE",
            "args": {"from_zone": args.get("from_zone"), "to_zone": args.get("to_zone")},
        }
    if action_type == "START_RUN":
        return {
            "action_index": ACTION_START_RUN,
            "action_type": "START_RUN",
            "args": {"device_id": args.get("device_id"), "work_id": args.get("work_id")},
        }
    return {"action_index": ACTION_NOOP}


class RippleEffectMethod(CoordinationMethod):
    """
    Ripple Effect Protocol: local intent, signed broadcast to neighbors via
    SignedMessageBus, conflict resolution (priority + tie-break). No central planner.
    """

    def __init__(
        self,
        key_store: dict[str, tuple[Any, str]],
        *,
        identity_policy: dict[str, Any] | None = None,
    ) -> None:
        policy = identity_policy or {}
        policy.setdefault("allowed_message_types", [MESSAGE_TYPE_RIPPLE_INTENT])
        self._key_store = key_store
        self._bus = SignedMessageBus(
            key_store=key_store,
            identity_policy=policy,
            epoch_fn=lambda: self._current_epoch,
        )
        self._current_epoch = 0
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._msg_count = 0
        self._invalid_sig_count = 0
        self._replay_drop_count = 0
        self._spoof_attempt_count = 0

    @property
    def method_id(self) -> str:
        return "ripple_effect"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._bus.reset()
        self._zone_ids, self._device_ids, self._device_zone = (
            extract_zone_and_device_ids(policy)
        )
        layout = (policy or {}).get("zone_layout") or {}
        self._adjacency = build_adjacency_set(layout.get("graph_edges") or [])
        self._current_epoch = 0
        self._msg_count = 0
        self._invalid_sig_count = 0
        self._replay_drop_count = 0
        self._spoof_attempt_count = 0

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {a: {"action_index": ACTION_NOOP} for a in agents}
        if not agents:
            return out
        if not self._zone_ids and obs:
            sample = next(iter(obs.values()))
            self._zone_ids, self._device_ids, self._device_zone = (
                extract_zone_and_device_ids({}, obs_sample=sample)
            )
        if not self._zone_ids:
            self._zone_ids = ["Z_SORTING_LANES"]
        if not self._adjacency:
            for z in self._zone_ids:
                self._adjacency.add((z, z))
        self._current_epoch = t

        agent_zone: dict[str, str] = {}
        for aid in agents:
            o = obs.get(aid) or {}
            agent_zone[aid] = (
                get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            )
        neighbor_graph = _build_neighbor_graph(
            agents, agent_zone, self._adjacency
        )
        if not neighbor_graph:
            neighbor_graph = {a: [b for b in agents if b != a] for a in agents}

        intents: list[tuple[str, dict[str, Any] | None]] = []
        envelopes: list[dict[str, Any]] = []
        for i, agent_id in enumerate(agents):
            intent = _compute_local_intent(
                agent_id,
                obs,
                self._zone_ids,
                self._device_ids,
                self._device_zone,
                t,
            )
            intents.append((agent_id, intent))
            if intent is not None:
                nonce = t * max(len(agents), 1) + i
                env = sign_message(
                    MESSAGE_TYPE_RIPPLE_INTENT,
                    intent,
                    agent_id,
                    nonce,
                    t,
                    self._key_store,
                )
                if env is not None:
                    envelopes.append(env)
                    self._msg_count += 1

        accepted: dict[str, dict[str, Any]] = {}
        for env in envelopes:
            accepted_bus, delivered, violation = self._bus.receive(env)
            if accepted_bus and delivered:
                sid = delivered.get(KEY_SENDER_ID)
                pl = delivered.get(KEY_PAYLOAD)
                if sid and isinstance(pl, dict):
                    accepted[sid] = pl
            elif violation:
                v_list = violation.get("violations") or [{}]
                reason = (v_list[0].get("reason_code") or "") if v_list else ""
                if reason == COORD_REPLAY_DETECTED:
                    self._replay_drop_count += 1
                elif reason == COORD_SIGNATURE_INVALID:
                    self._invalid_sig_count += 1
                    ok_any, actual_sender = verify_message_find_signer(
                        env, self._key_store
                    )
                    claimed = env.get(KEY_SENDER_ID)
                    if (
                        ok_any
                        and actual_sender
                        and claimed
                        and actual_sender != claimed
                    ):
                        self._spoof_attempt_count += 1

        intent_by_agent: dict[str, dict[str, Any] | None] = {
            aid: intent for aid, intent in intents
        }
        for agent_id in agents:
            own = intent_by_agent.get(agent_id)
            neighbors = neighbor_graph.get(agent_id) or []
            neighbor_payloads = [
                (sid, accepted[sid])
                for sid in neighbors
                if sid in accepted
            ]
            my_zone = agent_zone.get(agent_id) or ""
            resolved = _resolve_conflicts(
                agent_id,
                own,
                neighbor_payloads,
                self._device_zone,
                self._zone_ids,
                self._adjacency,
                my_zone,
            )
            out[agent_id] = _intent_to_action_dict(resolved)

        door_open = False
        for aid in agents:
            o = obs.get(aid) or {}
            if o.get("door_restricted_open") is not None:
                door_open = bool(
                    o.get("door_restricted_open", 0)
                    if not hasattr(o["door_restricted_open"], "item")
                    else o["door_restricted_open"].item()
                )
                break
        if door_open and t > 0 and t % 3 == 0:
            for aid in agents:
                if out[aid].get("action_index") == ACTION_NOOP:
                    out[aid] = {"action_index": ACTION_TICK}
                    break
        return out

    def get_comm_metrics(self) -> dict[str, Any]:
        """coordination.comm: msg_count, invalid_sig_count, replay_drop_count, spoof."""
        total = (
            self._msg_count
            + self._invalid_sig_count
            + self._replay_drop_count
        )
        invalid_rate = (
            self._invalid_sig_count / total if total > 0 else 0.0
        )
        return {
            "msg_count": self._msg_count,
            "drop_rate": 0.0,
            "invalid_sig_count": self._invalid_sig_count,
            "replay_drop_count": self._replay_drop_count,
            "invalid_msg_rate": round(invalid_rate, 4),
            "spoof_attempt_count": self._spoof_attempt_count,
        }
