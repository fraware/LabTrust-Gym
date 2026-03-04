"""
Deterministic scripted operations agent baseline (e.g. for ops_0 / scheduler).

Policy: STAT (stat-priority) work first, then EDF (earliest-deadline-first) on
stability deadline; conservative stability and temperature (override only if
configured); never use restricted doors without the required token; on QC
fail, route to alternate device or hold. Purely deterministic given observations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.envs.action_contract import ACTION_NOOP, ACTION_QUEUE_RUN, ACTION_TICK

DEFAULT_DEVICE_IDS: list[str] = [
    "DEV_CENTRIFUGE_BANK_01",
    "DEV_ALIQUOTER_01",
    "DEV_CHEM_A_01",
    "DEV_CHEM_B_01",
    "DEV_HAEM_01",
    "DEV_COAG_01",
]

# Default alternates (same zone / compatible); index -> list of indices
DEFAULT_ALTERNATE_DEVICES: dict[int, list[int]] = {
    2: [3],  # DEV_CHEM_A_01 -> DEV_CHEM_B_01
    3: [2],  # DEV_CHEM_B_01 -> DEV_CHEM_A_01
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


def _device_qc_pass(obs: dict[str, Any], device_idx: int) -> bool:
    """True if device at index has QC pass."""
    arr = obs.get("device_qc_pass")
    if arr is None:
        return True
    if hasattr(arr, "flat"):
        return bool(arr.flat[device_idx] if device_idx < arr.size else 1)
    if isinstance(arr, list | tuple) and device_idx < len(arr):
        return bool(arr[device_idx])
    return True


def _queue_length(obs: dict[str, Any], device_idx: int, max_len: int = 100) -> int:
    """Queue length for device at index."""
    arr = obs.get("queue_lengths")
    if arr is None:
        return 0
    if hasattr(arr, "flat"):
        return min(int(arr.flat[device_idx]) if device_idx < arr.size else 0, max_len)
    if isinstance(arr, list | tuple) and device_idx < len(arr):
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
        alternate_devices: dict[int, list[int]] | None = None,
        device_ids: list[str] | None = None,
        door_tick_threshold_s: float = 150.0,
        max_queue_len: int = 50,
        policy_path: Path | None = None,
        policy_dict: dict[str, Any] | None = None,
    ) -> None:
        policy: dict[str, Any] = {}
        if policy_dict is not None:
            policy = policy_dict
        else:
            try:
                from labtrust_gym.policy.scripted import load_scripted_ops_policy

                policy = load_scripted_ops_policy(
                    policy_path_arg=policy_path,
                    repo_root=None,
                    validate=True,
                )
            except Exception:
                pass
        self.request_override_if_configured = policy.get(
            "request_override_if_configured", request_override_if_configured
        )
        alt = policy.get("alternate_devices")
        if alt is not None:
            self.alternate_devices = {int(k): list(v) for k, v in alt.items()}
        else:
            self.alternate_devices = alternate_devices or dict(DEFAULT_ALTERNATE_DEVICES)
        self.device_ids = policy.get("device_ids") or device_ids or list(DEFAULT_DEVICE_IDS)
        self.door_tick_threshold_s = policy.get("door_tick_threshold_s", door_tick_threshold_s)
        self.max_queue_len = policy.get("max_queue_len", max_queue_len)

    def act(
        self,
        observation: dict[str, Any],
        agent_id: str = "ops_0",
    ) -> tuple[int, dict[str, Any]]:
        """
        Return (action_index, action_info). Purely deterministic.

        observation may include:
          - work_list: list of {work_id, priority, deadline_s, stability_ok, temp_ok, device_id}
            (device_id can be str or int index). If missing, [].
          - releasable_result_ids: list of result_ids that can be released (generated/held, QC pass).
          - log_frozen, door_restricted_open, door_restricted_duration_s,
          - queue_lengths, device_qc_pass, token_count_override, token_count_restricted.
        """
        action_info: dict[str, Any] = {}

        releasable = observation.get("releasable_result_ids") or []
        if releasable and isinstance(releasable, (list, tuple)) and len(releasable) > 0:
            rid = releasable[0]
            return (
                0,
                {
                    "action_type": "RELEASE_RESULT",
                    "args": {"result_id": str(rid)},
                    "reason_code": None,
                    "rationale": "scripted_ops: STAT then EDF; release first releasable",
                },
            )

        log_frozen = _scalar(observation.get("log_frozen"), 0)
        if log_frozen:
            return (
                ACTION_NOOP,
                {
                    **action_info,
                    "reason_code": "AGENT_SCRIPTED_NOOP",
                    "rationale": "scripted_ops: log frozen",
                },
            )

        door_open = _scalar(observation.get("door_restricted_open"), 0)
        door_duration = _float_scalar(
            observation.get("door_restricted_duration_s"),
            0.0,
        )
        if door_open and door_duration >= self.door_tick_threshold_s:
            return (
                ACTION_TICK,
                {
                    **action_info,
                    "reason_code": None,
                    "rationale": "scripted_ops: door tick threshold exceeded",
                },
            )

        work_list = observation.get("work_list")
        if not isinstance(work_list, (list, tuple)):
            work_list = []
        token_override = _scalar(observation.get("token_count_override"), 0)
        _scalar(observation.get("token_count_restricted"), 0)

        def can_queue_without_override(work: dict[str, Any]) -> bool:
            if work.get("stability_ok", True) and work.get("temp_ok", True):
                return True
            return bool(self.request_override_if_configured and token_override > 0)

        eligible = [w for w in work_list if isinstance(w, dict) and can_queue_without_override(w)]

        def has_any_qc_pass_device(work: dict[str, Any]) -> bool:
            device_id_raw = work.get("device_id")
            if device_id_raw is None:
                return False
            try:
                if isinstance(device_id_raw, str):
                    dev_idx = self.device_ids.index(device_id_raw)
                else:
                    dev_idx = int(device_id_raw) % len(self.device_ids)
            except (ValueError, TypeError):
                return False
            if _device_qc_pass(observation, dev_idx):
                return True
            for a in self.alternate_devices.get(dev_idx, []):
                if _device_qc_pass(observation, a):
                    return True
            return False

        if eligible and not any(has_any_qc_pass_device(w) for w in eligible):
            return (
                ACTION_NOOP,
                {
                    **action_info,
                    "reason_code": "ROUTE_DEVICE_UNAVAILABLE",
                    "rationale": "scripted_ops: no device with QC pass for any work",
                },
            )

        # STAT first, then EDF (by deadline_s)
        def key(w: dict[str, Any]) -> tuple[int, int]:
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
                "device_id": (self.device_ids[dev_idx] if dev_idx < len(self.device_ids) else ""),
                "priority": str(work.get("priority", "ROUTINE")),
                "reason_code": None,
                "rationale": "scripted_ops: STAT then EDF; queue run",
            }
            return (ACTION_QUEUE_RUN, action_info)

        return (
            ACTION_NOOP,
            {
                **action_info,
                "reason_code": "AGENT_SCRIPTED_NOOP",
                "rationale": "scripted_ops: no eligible work or all held",
            },
        )
