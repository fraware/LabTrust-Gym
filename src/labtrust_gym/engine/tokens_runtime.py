"""
In-engine token store: mint, consume, revoke, and validity checks.

Tokens represent authorizations or capabilities (e.g. dual approval, drift
override). Once consumed or revoked, a token is invalid for replay
protection; expired tokens are also invalid. Lifecycle: ACTIVE can become
CONSUMED, REVOKED, or EXPIRED. The engine uses this store for token_refs
on actions and for invariant checks.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.policy.tokens import Token, token_state_after_time


class TokenStore:
    """In-memory token store: token_id -> Token. Used by engine state."""

    def __init__(self) -> None:
        self._tokens: dict[str, Token] = {}
        self._next_id: int = 0

    def load_initial(self, tokens: list[dict[str, Any]]) -> None:
        """Load initial tokens from scenario initial_state.tokens."""
        for t in tokens or []:
            tok = Token.from_dict(t)
            self._tokens[tok.token_id] = tok

    def get(self, token_id: str) -> Token | None:
        """Return token by id or None."""
        return self._tokens.get(token_id)

    def mint_token(
        self,
        token_id: str,
        token_type: str,
        subject_type: str,
        subject_id: str,
        issued_at_ts_s: int,
        expires_at_ts_s: int,
        reason_code: str | None,
        approvals: list[dict[str, Any]],
    ) -> Token:
        """Create and store a new ACTIVE token. Raises if token_id exists."""
        if token_id in self._tokens:
            raise ValueError(f"Token already exists: {token_id}")
        tok = Token(
            token_id=token_id,
            token_type=token_type,
            state="ACTIVE",
            subject_type=subject_type,
            subject_id=subject_id,
            issued_at_ts_s=issued_at_ts_s,
            expires_at_ts_s=expires_at_ts_s,
            reason_code=reason_code,
            approvals=approvals,
        )
        self._tokens[token_id] = tok
        return tok

    def consume_token(self, token_id: str) -> None:
        """Mark token as CONSUMED (replay protection)."""
        tok = self._tokens.get(token_id)
        if tok:
            tok.state = "CONSUMED"

    def revoke_token(self, token_id: str) -> None:
        """Mark token as REVOKED."""
        tok = self._tokens.get(token_id)
        if tok:
            tok.state = "REVOKED"

    def is_valid(self, token_id: str, t_s: int) -> bool:
        """
        True if token exists, is ACTIVE, not expired at t_s, not consumed, not revoked.
        Replay protection: consumed or revoked or expired => invalid.
        """
        tok = self._tokens.get(token_id)
        if not tok:
            return False
        effective = token_state_after_time(tok, t_s)
        if effective != "ACTIVE":
            return False
        return True

    def validity_violation(self, token_id: str, t_s: int) -> str | None:
        """Violation id if invalid: INV-TOK-002 (expired/consumed), INV-TOK-006 (revoked)."""
        tok = self._tokens.get(token_id)
        if not tok:
            return "INV-TOK-002"
        if tok.state == "REVOKED":
            return "INV-TOK-006"
        if tok.state == "CONSUMED":
            return "INV-TOK-002"
        if t_s > tok.expires_at_ts_s:
            return "INV-TOK-002"
        return None

    def list_active_ids(self, subject_id: str | None = None) -> list[str]:
        """Token ids that are ACTIVE (optionally for subject_id)."""
        out = []
        for tid, tok in self._tokens.items():
            if tok.state != "ACTIVE":
                continue
            if subject_id is not None and tok.subject_id != subject_id:
                continue
            out.append(tid)
        return out
