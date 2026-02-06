"""
Tests for B004 online abuse controls: auth, rate limit, body size, concurrency.

- Unauthenticated requests fail when API key is set (401, SECURITY_ALERT).
- Rate limiting triggers 429 and abuse counters.
- Body size limit triggers 413.
- Concurrency limit triggers 503 (or 429) deterministically.
"""

from __future__ import annotations

import json
import threading
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
    """Return (status_code, response_headers_dict, body_bytes)."""
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
    except urllib.error.URLError as e:
        raise RuntimeError(f"Request failed: {e}") from e


def _start_server(config: OnlineConfig) -> tuple[object, int]:
    """Start server in daemon thread; return (server, port)."""
    server = create_server(config)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    return server, port


def test_unauthorized_when_api_key_required() -> None:
    """When LABTRUST_ONLINE_API_KEY is set, request without key returns 401 and logs SECURITY_ALERT."""
    get_abuse_counters().reset()
    config = OnlineConfig(
        api_key="secret-key-123",
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
        status, _, raw = _request(port)
        assert status == 401
        data = json.loads(raw.decode("utf-8"))
        assert data.get("code") == "auth_failure"
        assert "error" in data
        assert get_abuse_counters().snapshot()["auth_failures"] >= 1
    finally:
        server.shutdown()


def test_authorized_with_correct_key_succeeds() -> None:
    """When API key is set, request with correct key returns 200."""
    config = OnlineConfig(
        api_key="allowed-key",
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
        status, _, raw = _request(port, headers={"X-Api-Key": "allowed-key"})
        assert status == 200
        data = json.loads(raw.decode("utf-8"))
        assert data.get("status") == "ok"
    finally:
        server.shutdown()


def test_rate_limit_triggers_429_and_security_alert() -> None:
    """Exceeding rate limit returns 429 and increments rate_limit_hits."""
    get_abuse_counters().reset()
    # Very low rate so we exhaust bucket quickly (1 RPS, capacity ~2)
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=1.0,
        rate_limit_rps_per_ip=1.0,
        max_body_bytes=1024 * 1024,
        max_inflight=20,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_OFF,
        key_registry=(),
    )
    server, port = _start_server(config)
    try:
        # Send several requests quickly; after bucket is exhausted we get 429
        statuses = []
        for _ in range(10):
            status, _, _ = _request(port)
            statuses.append(status)
        assert 429 in statuses
        assert get_abuse_counters().snapshot()["rate_limit_hits"] >= 1
    finally:
        server.shutdown()


def test_body_too_large_triggers_413() -> None:
    """Request with Content-Length > max_body_bytes returns 413."""
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
        assert get_abuse_counters().snapshot()["body_too_large"] >= 1
    finally:
        server.shutdown()


def test_concurrency_limit_triggers_503() -> None:
    """When max_inflight=1, a second request while first is in-flight gets 503."""
    import socket
    import sys

    if sys.platform == "win32":
        pytest.skip("concurrency test flaky on Windows (socket/thread timing)")

    get_abuse_counters().reset()
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=100.0,
        rate_limit_rps_per_ip=100.0,
        max_body_bytes=1024 * 1024,
        max_inflight=1,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_OFF,
        key_registry=(),
    )
    server, port = _start_server(config)
    second_status: list[int] = []

    def block_first_request() -> None:
        # POST with Content-Length 5000 but send only 100 bytes; server blocks in read()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("127.0.0.1", port))
        sock.sendall(b"POST /v0/step HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 5000\r\n\r\n" + b"x" * 100)
        time.sleep(1.0)
        sock.close()

    try:
        t_block = threading.Thread(target=block_first_request)
        t_block.start()
        time.sleep(0.15)
        try:
            status, _, _ = _request(port)
            second_status.append(status)
        except Exception:
            second_status.append(-1)
        t_block.join(timeout=5)
        assert len(second_status) == 1
        assert second_status[0] == 503
        assert get_abuse_counters().snapshot()["too_many_inflight"] >= 1
    finally:
        server.shutdown()


def test_error_response_no_stack_trace() -> None:
    """Error responses are JSON with code and message; no internal stack trace."""
    config = OnlineConfig(
        api_key="required",
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_API_KEY,
        key_registry=(),
    )
    server, port = _start_server(config)
    try:
        status, _, raw = _request(port)
        assert status == 401
        data = json.loads(raw.decode("utf-8"))
        assert "error" in data
        assert "code" in data
        # No Python traceback or file paths in response body
        text = raw.decode("utf-8")
        assert "Traceback" not in text
        assert 'File "' not in text
    finally:
        server.shutdown()


def test_public_health_without_auth_when_key_not_set() -> None:
    """When API key is not set, GET /health returns 200 without auth."""
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
        status, _, raw = _request(port)
        assert status == 200
        assert json.loads(raw.decode("utf-8")).get("status") == "ok"
    finally:
        server.shutdown()
