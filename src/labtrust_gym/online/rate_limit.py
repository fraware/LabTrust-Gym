"""
Token-bucket rate limiters for per-key and per-IP limits.

Thread-safe; uses a simple in-memory bucket per key. No external dependencies.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class TokenBucket:
    """
    Single token bucket: refills at rate tokens per second, max capacity.

    allow() returns True if a token was consumed, False if rate exceeded.
    """

    __slots__ = ("_rate", "_capacity", "_tokens", "_last", "_lock")

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        if rate <= 0:
            rate = 0.1
        self._rate = float(rate)
        self._capacity = float(capacity if capacity is not None else max(1.0, 2 * rate))
        self._tokens = self._capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        """Consume one token if available; return True if allowed, False if rate exceeded."""
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self._capacity,
                self._tokens + (now - self._last) * self._rate,
            )
            self._last = now
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False


class KeyedTokenBuckets:
    """
    Per-key token buckets with the same rate and capacity.

    Thread-safe. Old keys are never removed (bounded by number of distinct
    keys that have been used); for production consider a TTL cache.
    """

    def __init__(self, rate: float, capacity: float | None = None) -> None:
        self._rate = rate
        self._capacity = capacity
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(rate, capacity)
        )
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Allow one request for key; returns True if allowed."""
        with self._lock:
            bucket = self._buckets[key]
        return bucket.allow()
