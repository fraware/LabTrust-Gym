"""
Token schema and dual-approval validation.

- Token dataclass: token_id, token_type, state, subject_type, subject_id,
  issued_at_ts_s, expires_at_ts_s, reason_code, approvals.
- validate_dual_approval: two distinct approvers, distinct keys, required roles
  by token type (from registry; configurable later). Lifecycle: ACTIVE -> CONSUMED,
  ACTIVE -> REVOKED, ACTIVE -> EXPIRED (by time).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml


TOKEN_STATES = ("ACTIVE", "CONSUMED", "EXPIRED", "REVOKED", "MINTED")


@dataclass
class Token:
    """Single token with lifecycle state."""

    token_id: str
    token_type: str
    state: str  # ACTIVE, CONSUMED, EXPIRED, REVOKED, MINTED
    subject_type: str
    subject_id: str
    issued_at_ts_s: int
    expires_at_ts_s: int
    reason_code: Optional[str]
    approvals: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """For serialization / initial_state.tokens."""
        return {
            "token_id": self.token_id,
            "token_type": self.token_type,
            "state": self.state,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "issued_at_ts_s": self.issued_at_ts_s,
            "expires_at_ts_s": self.expires_at_ts_s,
            "reason_code": self.reason_code,
            "approvals": self.approvals,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Token:
        """Build Token from dict (e.g. initial_state.tokens or mint args)."""
        return cls(
            token_id=str(d["token_id"]),
            token_type=str(d["token_type"]),
            state=str(d.get("state", "ACTIVE")),
            subject_type=str(d["subject_type"]),
            subject_id=str(d["subject_id"]),
            issued_at_ts_s=int(d["issued_at_ts_s"]),
            expires_at_ts_s=int(d["expires_at_ts_s"]),
            reason_code=d.get("reason_code"),
            approvals=list(d.get("approvals", [])),
        )


def load_token_registry(path: str | Path) -> Dict[str, Any]:
    """Load token_registry YAML. Returns dict with token_types."""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        raise
    reg = data.get("token_registry")
    if reg is None:
        raise PolicyLoadError(p, "missing top-level key 'token_registry'")
    return reg


def validate_dual_approval(
    approvals: List[Dict[str, Any]],
    token_type: str,
    registry: Dict[str, Any],
) -> tuple[bool, Optional[str]]:
    """
    Validate dual approval: two distinct approvers, distinct keys, required count.
    Returns (ok, violation_id). violation_id INV-TOK-001 when invalid.
    """
    token_types = registry.get("token_types") or {}
    meta = token_types.get(token_type)
    if not meta:
        return True, None  # unknown type: skip strict check
    required = int(meta.get("approvals_required", 1))
    if required != 2:
        return True, None
    if not approvals or len(approvals) < 2:
        return False, "INV-TOK-001"
    a0, a1 = approvals[0], approvals[1]
    agent0 = a0.get("approver_agent_id") if isinstance(a0, dict) else None
    agent1 = a1.get("approver_agent_id") if isinstance(a1, dict) else None
    key0 = a0.get("approver_key_id") if isinstance(a0, dict) else None
    key1 = a1.get("approver_key_id") if isinstance(a1, dict) else None
    if agent0 == agent1:
        return False, "INV-TOK-001"
    if key0 == key1:
        return False, "INV-TOK-001"
    return True, None


def token_state_after_time(token: Token, t_s: int) -> str:
    """Effective state: EXPIRED if t_s > expires_at_ts_s else token.state."""
    if t_s > token.expires_at_ts_s:
        return "EXPIRED"
    return token.state
