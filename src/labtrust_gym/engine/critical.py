"""
Critical results classification and mandatory notify/ack record.

- Classify result to CRIT_A / CRIT_B / none from policy thresholds.
- RELEASE_RESULT blocked until ACK_CRITICAL_RESULT recorded (required fields).
- NOTIFY_CRITICAL_RESULT, ACK_CRITICAL_RESULT, ESCALATE_CRITICAL_RESULT.
- comm_record_exists(result_id), notification_mode_required(result_id).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml

CRIT_NO_ACK = "CRIT_NO_ACK"
INV_CRIT_002 = "INV-CRIT-002"
INV_CRIT_004 = "INV-CRIT-004"


def load_critical_thresholds(path: str | Path) -> List[Dict[str, Any]]:
    """Load critical_thresholds YAML. Returns list of threshold entries."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        raise
    root = data.get("critical_thresholds")
    if root is None:
        raise PolicyLoadError(p, "missing top-level key 'critical_thresholds'")
    entries = root.get("defaults_rcpath2017") or root.get("thresholds") or []
    return list(entries) if isinstance(entries, list) else []


def classify_criticality(
    analyte_code: str,
    value: float,
    units: str,
    thresholds: List[Dict[str, Any]],
) -> str:
    """
    Classify result to CRIT_A, CRIT_B, or none based on threshold table.
    Returns "CRIT_A", "CRIT_B", or "none".
    """
    for t in thresholds or []:
        if t.get("analyte_code") != analyte_code or t.get("units") != units:
            continue
        low = t.get("low")
        high = t.get("high")
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "none"
        if low is not None and v < float(low):
            return (t.get("class") or "CRIT_A").upper()
        if high is not None and v > float(high):
            return (t.get("class") or "CRIT_A").upper()
    return "none"


def default_thresholds() -> List[Dict[str, Any]]:
    """Minimal thresholds when policy file missing (K, Na, etc.)."""
    return [
        {"analyte_code": "BIOCHEM_POTASSIUM_K", "units": "mmol/L", "low": 2.5, "high": 6.5, "class": "CRIT_A"},
        {"analyte_code": "BIOCHEM_SODIUM_NA", "units": "mmol/L", "low": 120, "high": 160, "class": "CRIT_A"},
    ]


class CriticalStore:
    """
    Result criticality and communication records.
    - result_criticality: result_id -> CRIT_A | CRIT_B | none
    - comm_records: result_id -> list of { type: notify|ack, ... }
    - has_ack(result_id): True if at least one ACK recorded with required fields.
    """

    def __init__(
        self,
        thresholds: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._thresholds = thresholds or []
        self._result_criticality: Dict[str, str] = {}
        self._comm_records: Dict[str, List[Dict[str, Any]]] = {}
        self._notification_mode_required: Dict[str, str] = {}

    def load_thresholds(self, thresholds: List[Dict[str, Any]]) -> None:
        self._thresholds = list(thresholds)

    def set_criticality(self, result_id: str, criticality: str) -> None:
        self._result_criticality[str(result_id)] = str(criticality).upper()

    def result_criticality(self, result_id: str) -> str:
        return self._result_criticality.get(result_id, "none")

    def classify_and_set(
        self,
        result_id: str,
        analyte_code: str,
        value: Any,
        units: str,
    ) -> str:
        """Classify and store criticality for result. Returns CRIT_A, CRIT_B, or none."""
        crit = classify_criticality(
            analyte_code, float(value) if value is not None else 0, units, self._thresholds
        )
        self.set_criticality(result_id, crit)
        return crit

    def record_notify(
        self,
        result_id: str,
        channel: str,
        receiver_role: str,
        agent_id: str,
        t_s: int,
    ) -> None:
        """Record NOTIFY_CRITICAL_RESULT."""
        self._comm_records.setdefault(result_id, []).append({
            "type": "notify",
            "channel": channel,
            "receiver_role": receiver_role,
            "sender_agent_id": agent_id,
            "communicated_ts": t_s,
        })

    def record_ack(
        self,
        result_id: str,
        args: Dict[str, Any],
        agent_id: str,
        t_s: int,
    ) -> tuple[bool, Optional[str]]:
        """
        Record ACK_CRITICAL_RESULT. Returns (read_back_ok, violation_id).
        read_back_ok: True if read_back_confirmed is True.
        violation_id: INV-CRIT-004 if read_back_confirmed is False.
        """
        rec = {
            "type": "ack",
            "result_id": result_id,
            "channel": args.get("channel"),
            "receiver_role": args.get("receiver_role"),
            "receiver_name_or_id": args.get("receiver_name_or_id"),
            "receiver_location_or_org": args.get("receiver_location_or_org"),
            "read_back_confirmed": args.get("read_back_confirmed"),
            "outcome": args.get("outcome"),
            "acknowledgment_ts_s": args.get("acknowledgment_ts_s", t_s),
            "sender_agent_id": agent_id,
        }
        self._comm_records.setdefault(result_id, []).append(rec)
        read_back = rec.get("read_back_confirmed")
        if read_back is False:
            return False, INV_CRIT_004
        return True, None

    def has_ack(self, result_id: str) -> bool:
        """True if at least one ACK record exists with required fields."""
        for r in self._comm_records.get(result_id, []):
            if r.get("type") != "ack":
                continue
            if all(
                r.get(k) is not None
                for k in (
                    "channel",
                    "receiver_role",
                    "receiver_name_or_id",
                    "receiver_location_or_org",
                    "read_back_confirmed",
                    "outcome",
                )
            ):
                return True
        return False

    def comm_record_exists(self, result_id: str) -> bool:
        """True if any comm record (notify or ack) exists for result_id."""
        return len(self._comm_records.get(result_id, [])) > 0

    def set_notification_mode_required(self, result_id: str, mode: str) -> None:
        """e.g. phone_or_bleep when downtime forces oral path."""
        self._notification_mode_required[result_id] = mode

    def notification_mode_required(self, result_id: str) -> Optional[str]:
        return self._notification_mode_required.get(result_id)
