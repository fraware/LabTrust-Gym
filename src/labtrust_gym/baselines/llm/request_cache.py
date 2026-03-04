"""
Request-level response cache for LLM backends (SOTA).

- Keys: hash of request (e.g. prompt_sha256 or messages digest).
- Values: (content, usage_dict) to avoid duplicate API calls for identical
  context;
- Bounded size (LRU eviction), optional TTL per entry.
- Opt-in via LABTRUST_LLM_REQUEST_CACHE=1; max size and TTL from env.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

# Defaults when cache enabled
DEFAULT_REQUEST_CACHE_MAX_SIZE = 256
DEFAULT_REQUEST_CACHE_TTL_S = 0  # 0 = no TTL, evict by size only


def _parse_request_cache_config() -> tuple[bool, int, int]:
    """Return (enabled, max_size, ttl_s)."""
    import os

    raw = (os.environ.get("LABTRUST_LLM_REQUEST_CACHE") or "").strip().lower()
    enabled = raw in ("1", "true", "yes")
    try:
        raw_size = os.environ.get("LABTRUST_LLM_REQUEST_CACHE_MAX_SIZE", "256")
        max_size = int(raw_size)
    except ValueError:
        max_size = DEFAULT_REQUEST_CACHE_MAX_SIZE
    max_size = max(1, min(max_size, 4096))
    try:
        ttl_s = int(os.environ.get("LABTRUST_LLM_REQUEST_CACHE_TTL_S", "0"))
    except ValueError:
        ttl_s = DEFAULT_REQUEST_CACHE_TTL_S
    ttl_s = max(0, ttl_s)
    return (enabled, max_size, ttl_s)


class _RequestCacheEntry:
    __slots__ = ("content", "usage", "ts")

    def __init__(self, content: str, usage: dict[str, Any]) -> None:
        self.content = content
        self.usage = usage
        self.ts = time.monotonic()


class RequestCache:
    """
    Thread-safe LRU cache for (key -> (content, usage)).
    Optional TTL: entries older than ttl_s are miss when ttl_s > 0.
    """

    def __init__(
        self,
        max_size: int = DEFAULT_REQUEST_CACHE_MAX_SIZE,
        ttl_s: int = DEFAULT_REQUEST_CACHE_TTL_S,
    ) -> None:
        self._max_size = max(1, max_size)
        self._ttl_s = max(0, ttl_s)
        self._order: OrderedDict[str, _RequestCacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[str, dict[str, Any]] | None:
        """Return (content, usage) if key present and not expired; else None."""
        with self._lock:
            entry = self._order.pop(key, None)
            if entry is None:
                return None
            age = time.monotonic() - entry.ts
            if self._ttl_s > 0 and age > self._ttl_s:
                return None
            self._order[key] = entry
            return (entry.content, entry.usage)

    def set(self, key: str, content: str, usage: dict[str, Any]) -> None:
        """Store entry; evict oldest if at capacity."""
        with self._lock:
            if key in self._order:
                self._order.move_to_end(key)
                self._order[key] = _RequestCacheEntry(content, usage)
                return
            while len(self._order) >= self._max_size and self._order:
                self._order.popitem(last=False)
            self._order[key] = _RequestCacheEntry(content, usage)


# Module-level cache instance (lazy init from env)
_request_cache: RequestCache | None = None
_request_cache_enabled = False


def get_request_cache() -> tuple[bool, RequestCache | None]:
    """Return (enabled, cache). Cache is created on first use when enabled."""
    global _request_cache, _request_cache_enabled
    enabled, max_size, ttl_s = _parse_request_cache_config()
    _request_cache_enabled = enabled
    if not enabled:
        return (False, None)
    if _request_cache is None:
        _request_cache = RequestCache(max_size=max_size, ttl_s=ttl_s)
    return (True, _request_cache)
