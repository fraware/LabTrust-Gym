"""
Deterministic, bounded, non-sensitive state digest for LLM central planner.

Builds a global state digest from obs (per-agent), infos, and step t:
- per_agent: zone, task, last_action, local queue length
- per_device: state, queue head, utilization (default when no timing)
- per_specimen: stage, priority (STAT/ROUTINE), SLA remaining (bounded count)
- comms_stats: msg_count, drop_rate
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.coordination.obs_utils import (
    extract_zone_and_device_ids,
    get_queue_by_device,
    get_zone_from_obs,
    log_frozen,
)

# Caps for bounded output (non-sensitive, token control)
MAX_AGENTS_DIGEST = 32
MAX_DEVICES_DIGEST = 24
MAX_SPECIMENS_DIGEST = 64
MAX_QUEUE_LEN_DIGEST = 10


def _scalar(x: Any, default: int = 0) -> int:
    if x is None:
        return default
    if hasattr(x, "item"):
        return int(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return int(x.flat[0]) if hasattr(x, "flat") else int(x[0])
    return int(x)


def build_state_digest(
    obs: dict[str, Any],
    infos: dict[str, dict[str, Any]],
    t: int,
    policy: dict[str, Any] | None = None,
    *,
    max_agents: int = MAX_AGENTS_DIGEST,
    max_devices: int = MAX_DEVICES_DIGEST,
    max_specimens: int = MAX_SPECIMENS_DIGEST,
) -> dict[str, Any]:
    """
    Build a deterministic, bounded state digest from observations and infos.

    Non-sensitive: no PII, no raw specimen ids in free text; stage/priority only.
    Bounded: lists capped by max_agents, max_devices, max_specimens.
    """
    policy = policy or {}
    zone_ids, device_ids, device_zone = extract_zone_and_device_ids(
        policy,
        obs_sample=next(iter(obs.values())) if obs else None,
    )
    if not zone_ids and obs:
        zone_ids = ["Z_SORTING_LANES"]
    if not device_ids and obs:
        sample = next(iter(obs.values()))
        qbd = get_queue_by_device(sample)
        for q in qbd[:max_devices]:
            if isinstance(q, dict) and q.get("device_id"):
                device_ids.append(str(q["device_id"]))
                device_zone[str(q["device_id"])] = ""

    per_agent: list[dict[str, Any]] = []
    for i, (agent_id, o) in enumerate(sorted(obs.items())):
        if i >= max_agents:
            break
        o = o or {}
        zone = get_zone_from_obs(o, zone_ids) or o.get("zone_id") or ""
        task = "frozen" if log_frozen(o) else "active"
        last_action = str(o.get("last_action_type") or "NOOP")
        qbd = get_queue_by_device(o)
        local_queue_len = sum(
            _scalar(q.get("queue_len"), 0) for q in qbd if isinstance(q, dict)
        )
        per_agent.append({
            "agent_id": str(agent_id),
            "zone": zone,
            "task": task,
            "last_action": last_action,
            "local_queue_len": min(local_queue_len, MAX_QUEUE_LEN_DIGEST),
        })

    per_device: list[dict[str, Any]] = []
    for i, dev_id in enumerate(device_ids[:max_devices]):
        if i >= max_devices:
            break
        state = "unknown"
        queue_head = ""
        utilization = 0.0
        if obs:
            sample = next(iter(obs.values()))
            qbd = get_queue_by_device(sample)
            for j, q in enumerate(qbd):
                if isinstance(q, dict) and q.get("device_id") == dev_id:
                    state = "busy" if _scalar(q.get("queue_len"), 0) > 0 else "idle"
                    queue_head = str(q.get("queue_head") or "")[:32]
                    utilization = min(
                        1.0,
                        _scalar(q.get("queue_len"), 0) / max(1, MAX_QUEUE_LEN_DIGEST),
                    )
                    break
        per_device.append({
            "device_id": str(dev_id),
            "state": state,
            "queue_head": queue_head,
            "utilization": round(utilization, 2),
        })

    per_specimen: list[dict[str, Any]] = []
    specimen_count = 0
    for agent_id, o in sorted(obs.items()):
        if specimen_count >= max_specimens:
            break
        o = o or {}
        spec_stage = str(o.get("specimen_stage") or "")[:24]
        spec_priority = str(o.get("specimen_priority") or "ROUTINE").upper()
        if "STAT" not in spec_priority and "URGENT" not in spec_priority:
            spec_priority = "ROUTINE"
        sla_remaining = _scalar(o.get("sla_remaining_steps"), -1)
        if spec_stage or sla_remaining >= 0:
            per_specimen.append({
                "stage": spec_stage or "unknown",
                "priority": spec_priority,
                "sla_remaining": sla_remaining,
            })
            specimen_count += 1

    comms_stats: dict[str, Any] = {"msg_count": 0, "drop_rate": 0.0}
    for info in (infos or {}).values():
        if not isinstance(info, dict):
            continue
        comms_stats["msg_count"] = comms_stats.get("msg_count", 0) + _scalar(
            info.get("comm_msg_count"), 0
        )
        dr = info.get("comm_drop_rate")
        if dr is not None:
            if hasattr(dr, "item"):
                comms_stats["drop_rate"] = float(dr.item())
            else:
                comms_stats["drop_rate"] = float(dr)
            break

    return {
        "step": t,
        "per_agent": per_agent,
        "per_device": per_device,
        "per_specimen": per_specimen[:max_specimens],
        "comms_stats": comms_stats,
    }
