"""
Tests for commit-reveal bids: commit, verify_reveal, replay rejection.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.allocation.commit_reveal import (
    accept_reveal,
    commit,
    verify_reveal,
)


def test_commit_deterministic() -> None:
    """Same inputs produce same hash."""
    h1 = commit("a1", 1.5, "n1", 0)
    h2 = commit("a1", 1.5, "n1", 0)
    assert h1 == h2


def test_verify_reveal_ok() -> None:
    """Valid reveal passes."""
    h = commit("a1", 2.0, "nonce_x", 1)
    seen: set[tuple[str, int, str]] = set()
    ok, reason = verify_reveal("a1", 2.0, "nonce_x", 1, h, seen)
    assert ok is True
    assert reason is None


def test_verify_reveal_mismatch() -> None:
    """Wrong bid fails with reveal_mismatch."""
    h = commit("a1", 2.0, "nonce_x", 1)
    seen: set[tuple[str, int, str]] = set()
    ok, reason = verify_reveal("a1", 2.1, "nonce_x", 1, h, seen)
    assert ok is False
    assert reason == "reveal_mismatch"


def test_verify_reveal_replay() -> None:
    """Replay fails with replay."""
    h = commit("a1", 2.0, "n1", 0)
    seen: set[tuple[str, int, str]] = set()
    accept_reveal(seen, "a1", 0, "n1")
    ok, reason = verify_reveal("a1", 2.0, "n1", 0, h, seen)
    assert ok is False
    assert reason == "replay"
