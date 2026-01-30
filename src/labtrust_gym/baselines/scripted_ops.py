"""
Deterministic scripted operations agent baseline.

Policy: STAT front-of-line, else EDF on stability deadline; conservative
stability/temp (override only if configured); never restricted without token;
QC fail => route to alternate device or hold. Purely deterministic given obs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Action indices aligned with pz_parallel
ACTION_NOOP = 0
ACTION_TICK = 1
ACTION_QUEUE_RUN = 2

DEFAULT_DEVICE_IDS: List[str] = [
    "DEV_CENTRIFUGE_BANK_01",
    "DEV_ALIQUOTER_01",
    "DEV_CHEM_A_01",
    "DEV_CHEM_B_01",
    "DEV_HAEM_01",
    "DEV_COAG_01",
]

# Default alternates (same zone / compatible); index -> list of indices
DEFAULT_ALTERNATE_DEVICES: Dict[int, List[int]] = {
    2: [3],   # DEV_CHEM_A_01 -> DEV_CHEM_B_01
    3: [2],   # DEV_CHEM_B_01 -> DEV_CHEM_A_01
    4: [2, 3],
    5: [3],
}


def _scalar(x: Any, default: int = 0) -> int:
    """Extract int from obs value (array or scalar)."""
    if x is None:
        return default
    if hasattr(x, "item"):
        return int(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return int(x.flat[0]) if hasattr(x, "flat") else int(x[0])
    return int(x)


def _float_scalar(x: Any, default: float = 0.0) -> float:
    """Extract float from obs value."""
    if x is None:
        return default
    if hasattr(x, "item"):
        return float(x.item())
    if hasattr(x, "__len__") and len(x) > 0:
        return float(x.flat[0]) if hasattr(x, "flat") else float(x[0])
    return float(x)


def _device_qc_pass(obs: Dict[str, Any], device_idx: int) -> bool:
    """True if device at index has QC pass."""
    arr = obs.get("device_qc_pass")
    if arr is None:
        return True
    if hasattr(arr, "flat"):
        return bool(arr.flat[device_idx] if device_idx < arr.size else 1)
    if isinstance(arr, (list, tuple)) and device_idx < len(arr):
        return bool(arr[device_idx])
    return True


def _queue_length(obs: Dict[str, Any], device_idx: int, max_len: int = 100) -> int:
    """Queue length for device at index."""
    arr = obs.get("queue_lengths")
    if arr is None:
        return 0
    if hasattr(arr, "flat"):
        return min(int(arr.flat[device_idx]) if device_idx < arr.size else 0, max_len)
    if isinstance(arr, (list, tuple)) and device_idx < len(arr):
        return min(int(arr[device_idx]), max_len)
    return 0


class ScriptedOpsAgent:
    """
    Deterministic scripted operations agent.

    Policy:
      1) STAT specimens always front-of-line: QUEUE_RUN with STAT priority.
      2) Else EDF on stability deadline (arrival_ts + stability_window).
      3) Conservative: stability borderline or temp out-of-band => request
         override token only if configured; otherwise HOLD (do not queue).
      4) Never attempts restricted actions without token.
      5) If QC fail on device, route to alternate if compatible; else hold.
    """

    def __init__(
        self,
        request_override_if_configured: bool = True,
        alternate_devices: Optional[Dict[int, List[int]]] = None,
        device_ids: Optional[List[str]] = None,
        door_tick_threshold_s: float = 150.0,
        max_queue_len: int = 50,
    ) -> None:
        self.request_override_if_configured = request_override_if_configured
        self.alternate_devices = alternate_devices or dict(DEFAULT_ALTERNATE_DEVICES)
        self.device_ids = device_ids or list(DEFAULT_DEVICE_IDS)
        self.door_tick_threshold_s = door_tick_threshold_s
        self.max_queue_len = max_queue_len

    def act(
        self,
        observation: Dict[str, Any],
        agent_id: str = "ops_0",
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Return (action_index, action_info). Purely deterministic.

        observation may include:
          - work_list: list of {work_id, priority, deadline_s, stability_ok, temp_ok, device_id}
            (device_id can be str or int index). If missing, [].
          - log_frozen, door_restricted_open, door_restricted_duration_s,
          - queue_lengths, device_qc_pass, token_count_override, token_count_restricted.
        """
        action_info: Dict[str, Any] = {}

        log_frozen = _scalar(observation.get("log_frozen"), 0)
        if log_frozen:
            return (ACTION_NOOP, action_info)

        door_open = _scalar(observation.get("door_restricted_open"), 0)
        door_duration = _float_scalar(
            observation.get("door_restricted_duration_s"),
            0.0,
        )
        if door_open and door_duration >= self.door_tick_threshold_s:
            return (ACTION_TICK, action_info)

        work_list = observation.get("work_list") or []
        token_override = _scalar(observation.get("token_count_override"), 0)
        token_restricted = _scalar(observation.get("token_count_restricted"), 0)

        def can_queue_without_override(work: Dict[str, Any]) -> bool:
            if work.get("stability_ok", True) and work.get("temp_ok", True):
                return True
            return bool(
                self.request_override_if_configured and token_override > 0
            )

        eligible = [w for w in work_list if can_queue_without_override(w)]
        # STAT first, then EDF (by deadline_s)
        def key(w: Dict[str, Any]) -> Tuple[int, int]:
            prio = 0 if (w.get("priority") == "STAT") else 1
            deadline = int(w.get("deadline_s", 0))
            return (prio, deadline)

        eligible.sort(key=key)

        for work in eligible:
            device_id_raw = work.get("device_id")
            if device_id_raw is None:
                continue
            if isinstance(device_id_raw, str):
                try:
                    dev_idx = self.device_ids.index(device_id_raw)
                except ValueError:
                    dev_idx = 0
            else:
                dev_idx = int(device_id_raw) % len(self.device_ids)

            if not _device_qc_pass(observation, dev_idx):
                alts = self.alternate_devices.get(dev_idx, [])
                dev_idx = -1
                for a in alts:
                    if _device_qc_pass(observation, a):
                        dev_idx = a
                        break
                if dev_idx < 0:
                    continue  # hold: no alternate with QC pass

            if _queue_length(observation, dev_idx, self.max_queue_len) >= self.max_queue_len:
                continue

            action_info = {
                "work_id": str(work.get("work_id", "")),
                "device_id": self.device_ids[dev_idx] if dev_idx < len(self.device_ids) else "",
                "priority": str(work.get("priority", "ROUTINE")),
            }
            return (ACTION_QUEUE_RUN, action_info)

        return (ACTION_NOOP, action_info)
