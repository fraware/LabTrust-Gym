"""
Commit-reveal bids: two-phase (submit hash(commit); next step reveal bid + nonce; verify).
Reject reveal mismatch or replay (epoch/nonce).
"""

from __future__ import annotations

import hashlib
from typing import Any


def commit(agent_id: str, bid: float, nonce: str, epoch: int = 0) -> str:
    """Produce commitment hash for (agent_id, bid, nonce, epoch)."""
    payload = f"{agent_id}|{bid}|{nonce}|{epoch}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_reveal(
    agent_id: str,
    bid: float,
    nonce: str,
    epoch: int,
    commitment_hash: str,
    seen_nonces: set[tuple[str, int, str]],
) -> tuple[bool, str | None]:
    """
    Verify reveal: hash matches and (agent_id, epoch, nonce) not seen (no replay).
    Returns (ok, reason_code). reason_code when reject: "reveal_mismatch" or "replay".
    """
    if (agent_id, epoch, nonce) in seen_nonces:
        return False, "replay"
    expected = commit(agent_id, bid, nonce, epoch)
    if expected != commitment_hash:
        return False, "reveal_mismatch"
    return True, None


def accept_reveal(seen_nonces: set[tuple[str, int, str]], agent_id: str, epoch: int, nonce: str) -> None:
    """Record (agent_id, epoch, nonce) to prevent replay."""
    seen_nonces.add((agent_id, epoch, nonce))
