"""
Online serve mode: HTTP API with abuse controls (B004).

- Optional API key, per-key and per-IP rate limits, body size and concurrency limits.
- Consistent error responses (no info leaks). SECURITY_ALERT telemetry for abuse events.
- Default: local-only binding; auth off unless LABTRUST_ONLINE_API_KEY is set.
"""

from __future__ import annotations

from labtrust_gym.online.config import load_online_config
from labtrust_gym.online.server import create_server, run_server

__all__ = [
    "create_server",
    "load_online_config",
    "run_server",
]
