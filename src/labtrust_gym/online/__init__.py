"""
Online serve mode: HTTP API for remote step/query with abuse controls.

Optional API key; per-key and per-IP rate limits; body size and concurrency
limits. Error responses are consistent and do not leak internal details.
Security telemetry records abuse events. Default: local-only binding; auth
required only when LABTRUST_ONLINE_API_KEY or LABTRUST_API_TOKEN is set.
"""

from __future__ import annotations

from labtrust_gym.online.config import load_online_config
from labtrust_gym.online.server import create_server, run_server

__all__ = [
    "create_server",
    "load_online_config",
    "run_server",
]
