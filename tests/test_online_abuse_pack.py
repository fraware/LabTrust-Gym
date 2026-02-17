"""
Abuse test pack: replay, rate limit, path traversal, oversized payload.

Deterministic tests using fixed fixtures; reuses server setup from test_online_abuse_controls.
Run in default pytest -m "not slow" when online server is available.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

import pytest

from labtrust_gym.online.config import AUTH_API_KEY, AUTH_OFF, OnlineConfig
from labtrust_gym.online.server import create_server
from labtrust_gym.online.telemetry import get_abuse_counters


def _url(port: int, path: str = "/health") -> str:
    return f"http://127.0.0.1:{port}{path}"


def _request(
    port: int,
    path: str = "/health",
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(
        _url(port, path),
        data=body,
        method=method,
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _start_server(config: OnlineConfig) -> tuple[object, int]:
    import threading
    server = create_server(config)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    return server, port


def test_abuse_pack_path_traversal_returns_404() -> None:
    """Path traversal attempts (paths containing '..') must not succeed; expect 404."""
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_OFF,
        key_registry=(),
    )
    server, port = _start_server(config)
    try:
        for path in ["/v0/../../../etc/passwd", "/..", "/v0/step/../../admin/keys"]:
            status, _, _ = _request(port, path=path)
            assert status == 404, f"Path {path!r} must return 404, got {status}"
    finally:
        server.shutdown()


def test_abuse_pack_oversized_payload_413() -> None:
    """Oversized request body must return 413 (entity_too_large)."""
    get_abuse_counters().reset()
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=100,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_OFF,
        key_registry=(),
    )
    server, port = _start_server(config)
    try:
        status, _, raw = _request(
            port,
            path="/v0/step",
            method="POST",
            body=b"x" * 200,
            headers={"Content-Length": "200"},
        )
        assert status == 413
        data = json.loads(raw.decode("utf-8"))
        assert data.get("code") == "entity_too_large"
    finally:
        server.shutdown()


def test_abuse_pack_rate_limit_exhaustion_429() -> None:
    """Rate limit exhaustion must trigger 429."""
    get_abuse_counters().reset()
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=2.0,
        rate_limit_rps_per_ip=2.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_OFF,
        key_registry=(),
    )
    server, port = _start_server(config)
    try:
        statuses = [_request(port)[0] for _ in range(8)]
        assert 429 in statuses
    finally:
        server.shutdown()


def test_abuse_pack_replay_same_auth_request_twice() -> None:
    """Same authenticated request sent twice: both succeed (idempotent); no replay rejection yet."""
    config = OnlineConfig(
        api_key="replay-test-key",
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_API_KEY,
        key_registry=(),
    )
    server, port = _start_server(config)
    try:
        headers = {"X-API-Key": "replay-test-key"}
        s1, _, _ = _request(port, headers=headers)
        s2, _, _ = _request(port, headers=headers)
        assert s1 == 200 and s2 == 200
    finally:
        server.shutdown()
