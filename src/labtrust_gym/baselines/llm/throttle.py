"""
Rate limiting and circuit breaker for LLM calls.

When the shield or pre-LLM check blocks repeatedly, the circuit breaker opens
and skips LLM calls for a cooldown period to avoid hammering the API. The rate
limiter caps the number of LLM calls per time window.
"""

from __future__ import annotations

import time
from typing import Any


class CircuitBreaker:
    """
    Opens after consecutive_blocks blocks (pre-LLM or shield); then skips LLM
    for cooldown_calls calls. Resets on first successful (non-block) decision.
    """

    def __init__(
        self,
        consecutive_threshold: int = 5,
        cooldown_calls: int = 10,
    ) -> None:
        self._consecutive_threshold = max(1, consecutive_threshold)
        self._cooldown_calls = max(0, cooldown_calls)
        self._consecutive_blocks = 0
        self._cooldown_remaining = 0

    def record_block(self) -> None:
        """Call when pre-LLM or shield blocked this step."""
        self._consecutive_blocks += 1
        if (
            self._consecutive_blocks >= self._consecutive_threshold
            and self._cooldown_calls > 0
        ):
            self._cooldown_remaining = self._cooldown_calls

    def record_success(self) -> None:
        """Call when LLM was called and decision was not blocked."""
        self._consecutive_blocks = 0

    def should_skip_llm(self) -> bool:
        """True if circuit is open (cooldown): skip LLM call and return NOOP."""
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return True
        return False

    def reset(self) -> None:
        """Reset state (e.g. at episode start)."""
        self._consecutive_blocks = 0
        self._cooldown_remaining = 0


class RateLimiter:
    """
    Limits LLM calls to max_calls per window_seconds (sliding window).
    Uses time.monotonic() for wall-clock window.
    """

    def __init__(
        self,
        max_calls: int = 60,
        window_seconds: float = 60.0,
    ) -> None:
        self._max_calls = max(1, max_calls)
        self._window_seconds = max(0.1, window_seconds)
        self._call_times: list[float] = []

    def allow_call(self) -> bool:
        """True if an LLM call is allowed under the rate limit."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        self._call_times = [t for t in self._call_times if t > cutoff]
        return len(self._call_times) < self._max_calls

    def record_call(self) -> None:
        """Call after an LLM call was made."""
        self._call_times.append(time.monotonic())

    def reset(self) -> None:
        """Clear call history (e.g. at episode start)."""
        self._call_times.clear()


def throttle_config_from_env() -> dict[str, Any]:
    """
    Read throttle config from environment (optional).
    LABTRUST_CIRCUIT_BREAKER_THRESHOLD, LABTRUST_CIRCUIT_BREAKER_COOLDOWN,
    LABTRUST_RATE_LIMIT_MAX_CALLS, LABTRUST_RATE_LIMIT_WINDOW_SECONDS.
    """
    import os

    out: dict[str, Any] = {}
    try:
        t = os.environ.get("LABTRUST_CIRCUIT_BREAKER_THRESHOLD", "").strip()
        if t.isdigit():
            out["circuit_consecutive_threshold"] = int(t)
    except Exception:
        pass
    try:
        c = os.environ.get("LABTRUST_CIRCUIT_BREAKER_COOLDOWN", "").strip()
        if c.isdigit():
            out["circuit_cooldown_calls"] = int(c)
    except Exception:
        pass
    try:
        m = os.environ.get("LABTRUST_RATE_LIMIT_MAX_CALLS", "").strip()
        if m.isdigit():
            out["rate_max_calls"] = int(m)
    except Exception:
        pass
    try:
        w = os.environ.get("LABTRUST_RATE_LIMIT_WINDOW_SECONDS", "").strip()
        if w:
            out["rate_window_seconds"] = float(w)
    except Exception:
        pass
    return out
