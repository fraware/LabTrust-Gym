"""
Episode-level structured logging: engine step results to JSONL.

Deterministic: same seed + actions => identical log (sort_keys, stable lists).
Compatible with later research analysis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO


def build_log_entry(
    event: Dict[str, Any],
    result: Dict[str, Any],
    partner_id: Optional[str] = None,
    policy_fingerprint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build one JSONL log entry from event and engine step result.

    Fields: t_s, agent_id, action_type, status, blocked_reason_code,
    emits, violations, token_consumed, hashchain_head (head_hash).
    Optional: args (for receipt export), hashchain (full), enforcements,
    partner_id, policy_fingerprint (when using partner overlay).
    Deterministic: violations and emits order preserved from engine.
    """
    t_s = int(event.get("t_s", 0))
    agent_id = str(event.get("agent_id", ""))
    action_type = str(event.get("action_type", ""))

    status = str(result.get("status", ""))
    blocked_reason_code = result.get("blocked_reason_code")
    if blocked_reason_code is not None:
        blocked_reason_code = str(blocked_reason_code)

    emits: List[str] = list(result.get("emits") or [])
    violations: List[Dict[str, Any]] = []
    for v in result.get("violations") or []:
        violations.append(
            {
                "invariant_id": v.get("invariant_id"),
                "status": v.get("status"),
                "reason_code": v.get("reason_code"),
            }
        )
    token_consumed: List[str] = list(result.get("token_consumed") or [])

    hashchain = result.get("hashchain") or {}
    hashchain_head = hashchain.get("head_hash")

    entry: Dict[str, Any] = {
        "t_s": t_s,
        "agent_id": agent_id,
        "action_type": action_type,
        "status": status,
        "blocked_reason_code": blocked_reason_code,
        "emits": emits,
        "violations": violations,
        "token_consumed": token_consumed,
        "hashchain_head": hashchain_head,
    }
    # Optional: args for receipt/evidence export (specimen_id, result_id, etc.)
    args = event.get("args")
    if args is not None and isinstance(args, dict):
        entry["args"] = args
    if hashchain:
        entry["hashchain"] = {
            "head_hash": hashchain.get("head_hash", ""),
            "length": hashchain.get("length", 0),
            "last_event_hash": hashchain.get("last_event_hash", ""),
        }
    enforcements = result.get("enforcements")
    if enforcements:
        entry["enforcements"] = list(enforcements)
    if partner_id is not None:
        entry["partner_id"] = partner_id
    if policy_fingerprint is not None:
        entry["policy_fingerprint"] = policy_fingerprint
    signature_verification = result.get("signature_verification")
    if signature_verification is not None and isinstance(signature_verification, dict):
        entry["signature_verification"] = signature_verification
    rbac_decision = result.get("rbac_decision")
    if rbac_decision is not None and isinstance(rbac_decision, dict):
        entry["rbac_decision"] = rbac_decision
    return entry


def write_log_line(stream: TextIO, entry: Dict[str, Any]) -> None:
    """
    Write one JSONL line (deterministic: sort_keys=True).

    Same entry => identical byte output.
    """
    line = json.dumps(entry, sort_keys=True) + "\n"
    stream.write(line)
    stream.flush()


class EpisodeLogger:
    """
    Writes episode step results to a JSONL file.

    One line per engine step (per agent). Deterministic output for
    same seed + actions. Open in append mode on first log_step.
    Optional partner_id and policy_fingerprint included when set.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        partner_id: Optional[str] = None,
        policy_fingerprint: Optional[str] = None,
    ) -> None:
        self._path = Path(path) if path else None
        self._stream: Optional[TextIO] = None
        self._partner_id = partner_id
        self._policy_fingerprint = policy_fingerprint

    def set_episode_meta(
        self,
        partner_id: Optional[str] = None,
        policy_fingerprint: Optional[str] = None,
    ) -> None:
        """Set partner_id and policy_fingerprint for this episode (e.g. at reset)."""
        if partner_id is not None:
            self._partner_id = partner_id
        if policy_fingerprint is not None:
            self._policy_fingerprint = policy_fingerprint

    def log_step(
        self,
        event: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Append one step (event + result) as a JSONL line."""
        if self._path is None:
            return
        if self._stream is None:
            self._stream = open(self._path, "a", encoding="utf-8")
        entry = build_log_entry(
            event,
            result,
            partner_id=self._partner_id,
            policy_fingerprint=self._policy_fingerprint,
        )
        write_log_line(self._stream, entry)

    def close(self) -> None:
        """Close the log file if open."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
