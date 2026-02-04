"""Shared observation parsing for coordination methods. Deterministic."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _scalar(x: Any, default: int = 0) -> int:
    if x is None:
        return default
    if hasattr(x, "item"):
        return int(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return int(x.flat[0]) if hasattr(x, "flat") else int(x[0])
    return int(x)


def _float_scalar(x: Any, default: float = 0.0) -> float:
    if x is None:
        return default
    if hasattr(x, "item"):
        return float(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return float(x.flat[0]) if hasattr(x, "flat") else float(x[0])
    return float(x)


def get_zone_from_obs(obs: Dict[str, Any], zone_ids: List[str]) -> Optional[str]:
    """Current zone id from obs (my_zone_idx 1-based into zone_ids)."""
    idx = _scalar(obs.get("my_zone_idx"), 0)
    if idx < 1 or idx > len(zone_ids):
        return None
    return zone_ids[idx - 1]


def get_queue_by_device(obs: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Queue state per device from obs.queue_by_device."""
    qbd = obs.get("queue_by_device")
    if isinstance(qbd, list):
        return list(qbd)
    return []


def get_zone_id_text(obs: Dict[str, Any]) -> str:
    """zone_id string from obs (state summary v0.2)."""
    z = obs.get("zone_id")
    return str(z) if z else ""


def queue_has_head(obs: Dict[str, Any], device_idx: int) -> bool:
    """True if device at index has queue head."""
    arr = obs.get("queue_has_head")
    if arr is None:
        return False
    if hasattr(arr, "flat"):
        return bool(arr.flat[device_idx] if device_idx < arr.size else 0)
    if isinstance(arr, (list, tuple)) and device_idx < len(arr):
        return bool(arr[device_idx])
    return False


def log_frozen(obs: Dict[str, Any]) -> bool:
    return _scalar(obs.get("log_frozen"), 0) != 0


def restricted_zone_frozen(obs: Dict[str, Any]) -> bool:
    return _scalar(obs.get("restricted_zone_frozen"), 0) != 0


def door_restricted_open(obs: Dict[str, Any]) -> bool:
    return _scalar(obs.get("door_restricted_open"), 0) != 0


def device_qc_pass(obs: Dict[str, Any], device_idx: int) -> bool:
    arr = obs.get("device_qc_pass")
    if arr is None:
        return True
    if hasattr(arr, "flat"):
        return bool(arr.flat[device_idx] if device_idx < arr.size else 1)
    if isinstance(arr, (list, tuple)) and device_idx < len(arr):
        return bool(arr[device_idx])
    return True


def extract_zone_and_device_ids(
    policy: Dict[str, Any],
    obs_sample: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], List[str], Dict[str, str]]:
    """
    Return (zone_ids, device_ids, device_zone_map) from policy or obs.
    device_zone_map: device_id -> zone_id.
    """
    zone_ids: List[str] = []
    device_ids: List[str] = []
    device_zone: Dict[str, str] = {}
    layout = (policy or {}).get("zone_layout") or {}
    placement = layout.get("device_placement") or []
    for p in placement:
        did = p.get("device_id")
        zid = p.get("zone_id")
        if did and zid:
            device_ids.append(did)
            device_zone[did] = zid
    zones_list = layout.get("zones") or []
    for z in zones_list:
        zid = z.get("zone_id") if isinstance(z, dict) else None
        if zid:
            zone_ids.append(zid)
    if not zone_ids and obs_sample:
        z = obs_sample.get("zone_id")
        if z:
            zone_ids = [str(z)]
    if not device_ids and obs_sample:
        qbd = get_queue_by_device(obs_sample)
        for q in qbd:
            did = q.get("device_id") if isinstance(q, dict) else None
            if did:
                device_ids.append(did)
                device_zone[did] = ""
    return zone_ids, device_ids, device_zone
