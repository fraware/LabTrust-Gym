"""
Critical results classification and mandatory notify/ack record.

v0.1: Classify result to CRIT_A / CRIT_B / none; RELEASE_RESULT blocked until ACK with required fields.
v0.2: Escalation ladder; NOTIFY creates attempt record (attempt_id, timestamp, caller_id, callee_role, mode,
      message_template_id, criticality_class); ACK must reference attempt_id and satisfy required_fields + readback;
      ESCALATE tier order and max_ack_wait_s enforced.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml

CRIT_NO_ACK = "CRIT_NO_ACK"
CRIT_ACK_MISSING_FIELDS = "CRIT_ACK_MISSING_FIELDS"
CRIT_ACK_TIMEOUT = "CRIT_ACK_TIMEOUT"
CRIT_ESCALATION_OUT_OF_ORDER = "CRIT_ESCALATION_OUT_OF_ORDER"
CRIT_MODE_NOT_ALLOWED = "CRIT_MODE_NOT_ALLOWED"
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


def load_escalation_ladder(path: str | Path | None = None) -> Optional[Dict[str, Any]]:
    """Load escalation_ladder v0.2 YAML. Returns dict with version, minimum_record_fields, tiers; or None if missing."""
    if path is None:
        p = Path("policy/critical/escalation_ladder.v0.2.yaml")
    else:
        p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        return None
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        return None
    if not data.get("tiers"):
        return None
    return data


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


def _tier_by_index(ladder: Dict[str, Any], tier_index: int) -> Optional[Dict[str, Any]]:
    for t in ladder.get("tiers") or []:
        if t.get("tier_index") == tier_index:
            return t
    return None


def _tier_by_role(ladder: Dict[str, Any], role: str) -> Optional[Dict[str, Any]]:
    for t in ladder.get("tiers") or []:
        if t.get("role") == role:
            return t
    return None


class CriticalStore:
    """
    Result criticality and communication records.
    v0.1: comm_records; has_ack = at least one ACK with required fields.
    v0.2 (when _ladder set): attempt records with attempt_id; ACK must reference attempt_id and satisfy
    minimum_record_fields + tier required_fields + readback when requires_readback; ESCALATE tier order enforced.
    """

    def __init__(
        self,
        thresholds: Optional[List[Dict[str, Any]]] = None,
        ladder: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._thresholds = thresholds or []
        self._ladder = ladder
        self._result_criticality: Dict[str, str] = {}
        self._comm_records: Dict[str, List[Dict[str, Any]]] = {}
        self._attempts: Dict[str, List[Dict[str, Any]]] = {}  # result_id -> list of attempt records (v0.2)
        self._notification_mode_required: Dict[str, str] = {}

    def load_thresholds(self, thresholds: List[Dict[str, Any]]) -> None:
        self._thresholds = list(thresholds)

    def load_ladder(self, ladder: Optional[Dict[str, Any]]) -> None:
        self._ladder = ladder

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
        message_template_id: Optional[str] = None,
        criticality_class: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Record NOTIFY_CRITICAL_RESULT.
        v0.2: Creates attempt record; validates mode in tier allowed_contact_modes.
        Returns (attempt_id, reason_code). attempt_id set on success; reason_code set on BLOCK (e.g. CRIT_MODE_NOT_ALLOWED).
        """
        rid = str(result_id)
        if self._ladder:
            tier = _tier_by_index(self._ladder, 0) if not self._attempts.get(rid) else None
            if tier is None and self._attempts.get(rid):
                tier = _tier_by_role(self._ladder, receiver_role) or _tier_by_index(self._ladder, 0)
            if tier is None:
                tier = _tier_by_index(self._ladder, 0)
            allowed = tier.get("allowed_contact_modes") or []
            mode = (channel or "").strip().lower()
            if allowed and mode and mode not in [m.lower() for m in allowed]:
                return None, CRIT_MODE_NOT_ALLOWED
            attempts_list = self._attempts.setdefault(rid, [])
            attempt_id = f"{rid}_attempt_{len(attempts_list)}"
            crit_class = criticality_class or self.result_criticality(rid)
            attempt = {
                "attempt_id": attempt_id,
                "timestamp": t_s,
                "caller_id": agent_id,
                "callee_role": receiver_role,
                "mode": mode or channel,
                "message_template_id": message_template_id or "",
                "criticality_class": crit_class,
                "tier_index": tier.get("tier_index", 0),
            }
            attempts_list.append(attempt)
            self._comm_records.setdefault(rid, []).append({
                "type": "notify",
                "attempt_id": attempt_id,
                "channel": channel,
                "receiver_role": receiver_role,
                "sender_agent_id": agent_id,
                "communicated_ts": t_s,
            })
            return attempt_id, None
        self._comm_records.setdefault(rid, []).append({
            "type": "notify",
            "channel": channel,
            "receiver_role": receiver_role,
            "sender_agent_id": agent_id,
            "communicated_ts": t_s,
        })
        return None, None

    def record_ack(
        self,
        result_id: str,
        args: Dict[str, Any],
        agent_id: str,
        t_s: int,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Record ACK_CRITICAL_RESULT.
        v0.1: Returns (read_back_ok, violation_id).
        v0.2: Validates attempt_id, required_fields, readback when required. Returns (ok, violation_id, reason_code).
        """
        rid = str(result_id)
        rec = {
            "type": "ack",
            "result_id": rid,
            "attempt_id": args.get("attempt_id"),
            "channel": args.get("channel"),
            "receiver_role": args.get("receiver_role"),
            "receiver_name_or_id": args.get("receiver_name_or_id"),
            "receiver_location_or_org": args.get("receiver_location_or_org"),
            "read_back_confirmed": args.get("read_back_confirmed"),
            "outcome": args.get("outcome"),
            "acknowledgment_ts_s": args.get("acknowledgment_ts_s", t_s),
            "sender_agent_id": agent_id,
        }
        if self._ladder:
            attempt_id = args.get("attempt_id")
            attempts_list = self._attempts.get(rid, [])
            if not attempt_id or not any(a.get("attempt_id") == attempt_id for a in attempts_list):
                return False, INV_CRIT_004, CRIT_ACK_MISSING_FIELDS
            attempt = next((a for a in attempts_list if a.get("attempt_id") == attempt_id), None)
            tier = _tier_by_index(self._ladder, attempt.get("tier_index", 0)) if attempt else None
            if tier is None:
                return False, INV_CRIT_004, CRIT_ACK_MISSING_FIELDS
            required = list(tier.get("required_fields") or [])
            for k in required:
                if rec.get(k) is None and args.get(k) is None:
                    return False, INV_CRIT_004, CRIT_ACK_MISSING_FIELDS
            if tier.get("requires_readback", True) and rec.get("read_back_confirmed") is False:
                self._comm_records.setdefault(rid, []).append(rec)
                return False, INV_CRIT_004, "CRIT_NO_READBACK"
            self._comm_records.setdefault(rid, []).append(rec)
            return True, None, None
        self._comm_records.setdefault(rid, []).append(rec)
        if rec.get("read_back_confirmed") is False:
            return False, INV_CRIT_004, "CRIT_NO_READBACK"
        return True, None, None

    def has_ack(self, result_id: str) -> bool:
        """True if at least one ACK record exists with required fields (v0.1) or compliant ack (v0.2)."""
        rid = str(result_id)
        if self._ladder:
            for r in self._comm_records.get(rid, []):
                if r.get("type") != "ack":
                    continue
                aid = r.get("attempt_id")
                if not aid:
                    continue
                attempts_list = self._attempts.get(rid, [])
                attempt = next((a for a in attempts_list if a.get("attempt_id") == aid), None)
                if not attempt:
                    continue
                tier = _tier_by_index(self._ladder, attempt.get("tier_index", 0))
                if not tier:
                    continue
                required = list(tier.get("required_fields") or [])
                if not all(r.get(k) is not None for k in required):
                    continue
                if tier.get("requires_readback", True) and r.get("read_back_confirmed") is not True:
                    continue
                return True
            return False
        for r in self._comm_records.get(rid, []):
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
        return len(self._comm_records.get(str(result_id), [])) > 0

    def set_notification_mode_required(self, result_id: str, mode: str) -> None:
        """e.g. phone_or_bleep when downtime forces oral path."""
        self._notification_mode_required[str(result_id)] = mode

    def notification_mode_required(self, result_id: str) -> Optional[str]:
        return self._notification_mode_required.get(str(result_id))

    def can_escalate(self, result_id: str, now_s: int) -> bool:
        """True if latest attempt has exceeded max_ack_wait_s and no compliant ack yet (v0.2 only)."""
        if not self._ladder:
            return False
        rid = str(result_id)
        attempts_list = self._attempts.get(rid, [])
        if not attempts_list:
            return False
        if self.has_ack(rid):
            return False
        latest = attempts_list[-1]
        tier = _tier_by_index(self._ladder, latest.get("tier_index", 0))
        if not tier:
            return False
        max_wait = int(tier.get("max_ack_wait_s", 0))
        if now_s - int(latest.get("timestamp", 0)) < max_wait:
            return False
        return True

    def record_escalate(
        self,
        result_id: str,
        next_role: str,
        agent_id: str,
        t_s: int,
        message_template_id: Optional[str] = None,
        criticality_class: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Record ESCALATE_CRITICAL_RESULT (v0.2). Appends new attempt at next tier.
        Returns (ok, reason_code). reason_code CRIT_ESCALATION_OUT_OF_ORDER if tier order violated.
        """
        rid = str(result_id)
        if not self._ladder:
            self._comm_records.setdefault(rid, []).append({
                "type": "escalate",
                "sender_agent_id": agent_id,
                "communicated_ts": t_s,
            })
            return True, None
        attempts_list = self._attempts.get(rid, [])
        current_tier_index = attempts_list[-1].get("tier_index", 0) if attempts_list else -1
        next_tier = _tier_by_role(self._ladder, next_role)
        if not next_tier:
            return False, CRIT_ESCALATION_OUT_OF_ORDER
        next_index = next_tier.get("tier_index", current_tier_index + 1)
        if next_index != current_tier_index + 1:
            return False, CRIT_ESCALATION_OUT_OF_ORDER
        attempt_id = f"{rid}_attempt_{len(attempts_list)}"
        crit_class = criticality_class or self.result_criticality(rid)
        attempt = {
            "attempt_id": attempt_id,
            "timestamp": t_s,
            "caller_id": agent_id,
            "callee_role": next_role,
            "mode": "",
            "message_template_id": message_template_id or "",
            "criticality_class": crit_class,
            "tier_index": next_index,
        }
        attempts_list.append(attempt)
        self._comm_records.setdefault(rid, []).append({
            "type": "escalate",
            "attempt_id": attempt_id,
            "next_role": next_role,
            "sender_agent_id": agent_id,
            "communicated_ts": t_s,
        })
        return True, None
