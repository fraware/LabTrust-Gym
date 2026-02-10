"""
Distributed method: each agent summarizes local state into a signed typed message;
deterministic consensus merges messages into a shared view. Uses SignedMessageBus
(epoch binding, replay protection). Max message size, typed fields only,
deterministic validator, poison detection heuristics. Logs detection events and
reason-coded drops for invalid messages.
"""

from __future__ import annotations

import json
from pathlib import Path
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
from labtrust_gym.coordination.bus import SignedMessageBus
from labtrust_gym.coordination.identity import (
    KEY_EPOCH,
    KEY_MESSAGE_TYPE,
    KEY_NONCE,
    KEY_PAYLOAD,
    KEY_SENDER_ID,
    build_key_store,
    sign_message,
)
from labtrust_gym.engine.zones import build_adjacency_set

MESSAGE_TYPE_GOSSIP_SUMMARY = "gossip_summary"
MAX_MESSAGE_PAYLOAD_BYTES = 4096
COORD_PAYLOAD_INVALID = "COORD_PAYLOAD_INVALID"
COORD_PAYLOAD_TOO_LARGE = "COORD_PAYLOAD_TOO_LARGE"
COORD_POISON_SUSPECTED = "COORD_POISON_SUSPECTED"


def _load_message_schema(repo_root: Path | None) -> dict[str, Any]:
    """Load coordination_message.v0.1.schema.json."""
    if repo_root is not None and (repo_root / "policy" / "schemas").exists():
        path = repo_root / "policy" / "schemas" / "coordination_message.v0.1.schema.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    try:
        from labtrust_gym.config import get_repo_root
        root = get_repo_root()
        path = root / "policy" / "schemas" / "coordination_message.v0.1.schema.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def validate_message_payload(
    payload: dict[str, Any],
    schema: dict[str, Any],
    *,
    max_bytes: int = MAX_MESSAGE_PAYLOAD_BYTES,
) -> tuple[bool, str]:
    """
    Strict validation: schema (no unknown fields), max size. Returns (valid, reason).
    """
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(raw.encode("utf-8")) > max_bytes:
        return False, COORD_PAYLOAD_TOO_LARGE
    if not schema:
        return True, ""
    try:
        import jsonschema
    except ImportError:
        return True, ""
    try:
        jsonschema.validate(instance=payload, schema=schema)
    except jsonschema.ValidationError as e:
        return False, f"{COORD_PAYLOAD_INVALID}: {str(e)}"
    return True, ""


def poison_heuristic(payload: dict[str, Any]) -> tuple[bool, str]:
    """
    Simple poison detection: suspicious substrings in string fields, or abnormal length.
    Returns (suspected, reason_code).
    """
    raw = json.dumps(payload)
    lower = raw.lower()
    if "ignore" in lower and ("previous" in lower or "instruction" in lower):
        return True, COORD_POISON_SUSPECTED
    if len(raw) > 3000 and payload.get("queue_summary") and len(payload["queue_summary"]) > 20:
        return True, COORD_POISON_SUSPECTED
    for key, val in payload.items():
        if isinstance(val, str) and len(val) > 512:
            return True, COORD_POISON_SUSPECTED
        if key == "queue_summary" and isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    for k, v in item.items():
                        if isinstance(v, str) and len(v) > 128:
                            return True, COORD_POISON_SUSPECTED
    return False, ""


def _is_valid_gossip_payload(payload: Any) -> bool:
    """Return True if payload is a valid gossip summary dict for signing."""
    if not isinstance(payload, dict):
        return False
    if not all(k in payload for k in ("agent_id", "step_id", "zone_id", "queue_summary", "task")):
        return False
    if not isinstance(payload.get("queue_summary"), list):
        return False
    return True


def _build_local_summary(
    agent_id: str,
    obs: dict[str, Any],
    zone_ids: list[str],
    device_ids: list[str],
    t: int,
) -> dict[str, Any]:
    """Build typed payload from agent obs (deterministic, bounded)."""
    o = obs.get(agent_id) or {}
    zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
    task = "frozen" if log_frozen(o) else "active"
    queue_summary: list[dict[str, Any]] = []
    qbd = get_queue_by_device(o)
    for idx, dev_id in enumerate(device_ids[:24]):
        if idx >= len(qbd):
            break
        d = qbd[idx] if isinstance(qbd[idx], dict) else {}
        queue_summary.append({
            "device_id": str(d.get("device_id", dev_id))[:32],
            "queue_len": min(1024, max(0, int(d.get("queue_len", 0)))),
            "queue_head": str(d.get("queue_head", ""))[:64],
        })
    return {
        "agent_id": agent_id[:64],
        "step_id": t,
        "zone_id": zone[:64],
        "queue_summary": queue_summary,
        "task": task,
    }


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


class LLMGossipSummarizer(CoordinationMethod):
    """
    Each agent summarizes local state into a signed typed message; deterministic
    consensus merges accepted messages into shared view. SignedMessageBus provides
    epoch binding and replay protection. Max message size, typed validator, poison
    heuristics. Logs detection_events and reason-coded drops.
    """

    def __init__(
        self,
        key_store: dict[str, tuple[Any, str]],
        *,
        repo_root: Path | None = None,
        identity_policy: dict[str, Any] | None = None,
        summary_backend: Any | None = None,
    ) -> None:
        self._key_store = key_store
        self._repo_root = repo_root
        self._summary_backend = summary_backend
        self._schema = _load_message_schema(repo_root)
        policy = identity_policy or {}
        policy.setdefault(
            "allowed_message_types",
            [MESSAGE_TYPE_GOSSIP_SUMMARY],
        )
        self._bus = SignedMessageBus(
            key_store=key_store,
            identity_policy=policy,
            epoch_fn=lambda: self._current_epoch,
        )
        self._current_epoch = 0
        self._seed = 0
        self._zone_ids: list[str] = []
        self._device_ids: list[str] = []
        self._device_zone: dict[str, str] = {}
        self._adjacency: set[tuple[str, str]] = set()
        self._detection_events: list[dict[str, Any]] = []
        self._drop_reasons: list[dict[str, Any]] = []

    @property
    def method_id(self) -> str:
        return "llm_gossip_summarizer"

    def reset(
        self,
        seed: int,
        policy: dict[str, Any],
        scale_config: dict[str, Any],
    ) -> None:
        self._seed = seed
        self._bus.reset()
        self._detection_events = []
        self._drop_reasons = []
        self._zone_ids, self._device_ids, self._device_zone = extract_zone_and_device_ids(
            policy
        )
        layout = (policy or {}).get("zone_layout") or {}
        self._adjacency = build_adjacency_set(
            layout.get("graph_edges") or []
        )

    def propose_actions(
        self,
        obs: dict[str, Any],
        infos: dict[str, dict[str, Any]],
        t: int,
    ) -> dict[str, dict[str, Any]]:
        agents = sorted(obs.keys())
        out: dict[str, dict[str, Any]] = {
            a: {"action_index": ACTION_NOOP, "action_type": "NOOP"}
            for a in agents
        }
        if (not self._zone_ids or not self._device_ids) and obs:
            sample = next(iter(obs.values()))
            self._zone_ids, self._device_ids, self._device_zone = (
                extract_zone_and_device_ids({}, obs_sample=sample)
            )
        if not self._zone_ids:
            self._zone_ids = ["Z_SORTING_LANES"]
        self._current_epoch = t

        envelopes: list[dict[str, Any]] = []
        for i, agent_id in enumerate(agents):
            if self._summary_backend is not None and hasattr(
                self._summary_backend, "get_summary"
            ):
                try:
                    payload = self._summary_backend.get_summary(
                        agent_id, obs, self._zone_ids, self._device_ids, t
                    )
                except Exception:
                    payload = None
                if not _is_valid_gossip_payload(payload):
                    payload = _build_local_summary(
                        agent_id, obs, self._zone_ids, self._device_ids, t
                    )
            else:
                payload = _build_local_summary(
                    agent_id, obs, self._zone_ids, self._device_ids, t
                )
            ok, reason = validate_message_payload(
                payload, self._schema, max_bytes=MAX_MESSAGE_PAYLOAD_BYTES
            )
            if not ok:
                self._drop_reasons.append({
                    "reason_code": reason,
                    "agent_id": agent_id,
                    "step_id": t,
                })
                continue
            suspected, poison_reason = poison_heuristic(payload)
            if suspected:
                self._detection_events.append({
                    "reason_code": poison_reason,
                    "agent_id": agent_id,
                    "step_id": t,
                })
                self._drop_reasons.append({
                    "reason_code": poison_reason,
                    "agent_id": agent_id,
                    "step_id": t,
                })
                continue
            nonce = t * max(len(agents), 1) + i
            env = sign_message(
                MESSAGE_TYPE_GOSSIP_SUMMARY,
                payload,
                agent_id,
                nonce,
                t,
                self._key_store,
            )
            if env is not None:
                envelopes.append(env)

        shared_view: dict[str, dict[str, Any]] = {}
        for env in envelopes:
            accepted, delivered, violation = self._bus.receive(env)
            if accepted and delivered:
                sid = delivered.get(KEY_SENDER_ID)
                pl = delivered.get(KEY_PAYLOAD)
                if sid and isinstance(pl, dict):
                    shared_view[sid] = pl
            elif violation:
                self._drop_reasons.append({
                    "reason_code": (
                        violation.get("violations") or [{}]
                    )[0].get("reason_code", "COORD_VIOLATION"),
                    "sender_id": env.get(KEY_SENDER_ID),
                    "step_id": t,
                })
                self._detection_events.append({
                    "reason_code": (
                        violation.get("violations") or [{}]
                    )[0].get("reason_code"),
                    "sender_id": env.get(KEY_SENDER_ID),
                    "step_id": t,
                })

        load: dict[str, tuple[str, int]] = {}
        for aid in agents:
            o = obs.get(aid) or {}
            z = get_zone_from_obs(o, self._zone_ids) or o.get("zone_id") or ""
            load[aid] = (z, 0)
        for sid, pl in shared_view.items():
            z = (pl.get("zone_id") or "")[:64]
            load[sid] = (z, load.get(sid, (z, 0))[1] + 1)

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
        worklist = list(dict.fromkeys(worklist))

        used_work: set[tuple[str, str]] = set()
        for device_id, work_id, zone_id in worklist:
            if (device_id, work_id) in used_work:
                continue
            candidates = [
                (aid, load.get(aid, ("", 0))[1])
                for aid in agents
                if not log_frozen(obs.get(aid) or {})
                and load.get(aid, ("", ""))[0] == zone_id
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
            for i, dev_id in enumerate(self._device_ids):
                if i < len(qbd) and (qbd[i].get("queue_len") or 0) > 0:
                    goal = self._device_zone.get(dev_id, goal)
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

    def get_detection_events(self) -> list[dict[str, Any]]:
        """Detection events and reason-coded drops for runner logging."""
        return list(self._detection_events)

    def get_drop_reasons(self) -> list[dict[str, Any]]:
        """Reason-coded drops (invalid messages, violations)."""
        return list(self._drop_reasons)
