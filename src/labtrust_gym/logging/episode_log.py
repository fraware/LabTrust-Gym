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
) -> Dict[str, Any]:
    """
    Build one JSONL log entry from event and engine step result.

    Fields: t_s, agent_id, action_type, status, blocked_reason_code,
    emits, violations, token_consumed, hashchain_head (head_hash).
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
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else None
        self._stream: Optional[TextIO] = None

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
        entry = build_log_entry(event, result)
        write_log_line(self._stream, entry)

    def close(self) -> None:
        """Close the log file if open."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
