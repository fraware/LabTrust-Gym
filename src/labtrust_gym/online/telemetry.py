"""
Abuse telemetry: SECURITY_ALERT events and aggregate counters for server logs.

No external calls. Emits structured JSON lines to a logger and maintains
in-memory counters for tests and operational visibility.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

# Reason codes from policy (online endpoint abuse)
ONLINE_AUTH_FAILURE = "ONLINE_AUTH_FAILURE"
ONLINE_FORBIDDEN = "ONLINE_FORBIDDEN"
ONLINE_RATE_LIMIT = "ONLINE_RATE_LIMIT"
ONLINE_BODY_TOO_LARGE = "ONLINE_BODY_TOO_LARGE"
ONLINE_TOO_MANY_INFLIGHT = "ONLINE_TOO_MANY_INFLIGHT"

_logger = logging.getLogger("labtrust_gym.online")


@dataclass
class AbuseCounters:
    """Thread-safe aggregate counters for abuse events."""

    auth_failures: int = 0
    forbidden: int = 0
    rate_limit_hits: int = 0
    body_too_large: int = 0
    too_many_inflight: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment(self, reason_code: str) -> None:
        with self._lock:
            if reason_code == ONLINE_AUTH_FAILURE:
                self.auth_failures += 1
            elif reason_code == ONLINE_FORBIDDEN:
                self.forbidden += 1
            elif reason_code == ONLINE_RATE_LIMIT:
                self.rate_limit_hits += 1
            elif reason_code == ONLINE_BODY_TOO_LARGE:
                self.body_too_large += 1
            elif reason_code == ONLINE_TOO_MANY_INFLIGHT:
                self.too_many_inflight += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "auth_failures": self.auth_failures,
                "forbidden": self.forbidden,
                "rate_limit_hits": self.rate_limit_hits,
                "body_too_large": self.body_too_large,
                "too_many_inflight": self.too_many_inflight,
            }

    def reset(self) -> None:
        with self._lock:
            self.auth_failures = 0
            self.forbidden = 0
            self.rate_limit_hits = 0
            self.body_too_large = 0
            self.too_many_inflight = 0


# Module-level counters so tests and server share the same instance
_abuse_counters = AbuseCounters()


def get_abuse_counters() -> AbuseCounters:
    return _abuse_counters


def emit_security_alert(
    reason_code: str,
    detail: str | None = None,
    counters: AbuseCounters | None = None,
    request_id: str | None = None,
) -> None:
    """
    Emit a SECURITY_ALERT event: structured log line and increment counters.

    Does not leak internal state. detail should be generic (e.g. "per_ip", "per_key").
    request_id: optional correlation id for log correlation (B007).
    """
    c = counters if counters is not None else _abuse_counters
    c.increment(reason_code)
    payload: dict[str, Any] = {
        "event": "SECURITY_ALERT",
        "reason_code": reason_code,
    }
    if detail is not None:
        payload["detail"] = detail
    if request_id is not None:
        payload["request_id"] = request_id
    _logger.warning("%s", json.dumps(payload))
