"""
Tests for B007 online authorization: auth modes, roles, request_id.

- OFF: all endpoints accessible without key; X-Request-Id present.
- API_KEY: single key grants admin; missing/invalid key -> 401 + SECURITY_ALERT with request_id.
- MULTI_KEY: viewer/runner/admin keys get least-privilege access; 403 + SECURITY_ALERT on privilege violation.
"""

from __future__ import annotations

import http.client
import json
import sys
import threading
import time
import urllib.error
import urllib.request

from labtrust_gym.online.config import (
    AUTH_API_KEY,
    AUTH_MULTI_KEY,
    AUTH_OFF,
    OnlineConfig,
)
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
    except (ConnectionResetError, OSError) as e:
        raise RuntimeError(f"Request failed: {e}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Request failed: {e}") from e


def _request_post(
    port: int,
    path: str,
    body: bytes = b"{}",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict, bytes]:
    """POST with explicit Content-Length (avoids chunked encoding). Returns (status, headers_dict, body)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
    if headers:
        h.update(headers)
    try:
        conn.request("POST", path, body=body, headers=h)
        resp = conn.getresponse()
        return resp.status, dict(resp.headers), resp.read()
    except (ConnectionResetError, OSError) as e:
        raise RuntimeError(f"Request failed: {e}") from e
    finally:
        conn.close()


def _start_server(config: OnlineConfig) -> tuple[object, int]:
    """Start server in daemon thread; return (server, port)."""
    server = create_server(config)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    return server, port


def test_auth_off_all_endpoints_accessible() -> None:
    """With auth_mode=off, all endpoints are accessible without API key."""
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
        for path in ["/", "/health", "/v0/summary"]:
            status, headers, raw = _request(port, path=path)
            assert status == 200, path
            assert "X-Request-Id" in headers or "x-request-id" in [h.lower() for h in headers]
        if sys.platform != "win32":
            status, _, raw = _request_post(port, "/v0/step", b"{}")
            assert status == 501, raw.decode("utf-8") if raw else "no body"
    finally:
        server.shutdown()


def test_auth_off_x_request_id_present() -> None:
    """Responses include X-Request-Id for correlation."""
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
        _, headers, _ = _request(port)
        req_id = headers.get("X-Request-Id") or headers.get("x-request-id")
        assert req_id is not None and len(req_id) > 0
    finally:
        server.shutdown()


def test_api_key_missing_returns_401_and_security_alert() -> None:
    """With api_key mode, request without key returns 401 and increments auth_failures."""
    get_abuse_counters().reset()
    config = OnlineConfig(
        api_key="admin-key",
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
        status, headers, raw = _request(port)
        assert status == 401
        data = json.loads(raw.decode("utf-8"))
        assert data.get("code") == "auth_failure"
        assert get_abuse_counters().snapshot()["auth_failures"] >= 1
        assert headers.get("X-Request-Id") or headers.get("x-request-id")
    finally:
        server.shutdown()


def test_api_key_valid_grants_admin_access() -> None:
    """With api_key mode, valid key gets admin: /health, /v0/summary, /v0/step, /v0/export, /admin/*."""
    config = OnlineConfig(
        api_key="admin-key",
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
        h = {"X-Api-Key": "admin-key"}
        assert _request(port, path="/health", headers=h)[0] == 200
        assert _request(port, path="/v0/summary", headers=h)[0] == 200
        assert _request(port, path="/v0/export", headers=h)[0] == 200
        assert _request(port, path="/admin/status", headers=h)[0] == 200
        if sys.platform != "win32":
            status, _, _ = _request_post(port, "/v0/step", b"{}", h)
            assert status == 501
    finally:
        server.shutdown()


def test_multi_key_invalid_returns_401() -> None:
    """With multi_key mode, invalid or missing key returns 401."""
    get_abuse_counters().reset()
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_MULTI_KEY,
        key_registry=(
            {"key": "viewer-k", "role": "viewer"},
            {"key": "runner-k", "role": "runner"},
            {"key": "admin-k", "role": "admin"},
        ),
    )
    server, port = _start_server(config)
    try:
        status, _, raw = _request(port)
        assert status == 401
        assert json.loads(raw.decode("utf-8")).get("code") == "auth_failure"
        assert get_abuse_counters().snapshot()["auth_failures"] >= 1
    finally:
        server.shutdown()


def test_multi_key_viewer_can_access_health_and_summary() -> None:
    """Viewer key can GET /health and GET /v0/summary."""
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_MULTI_KEY,
        key_registry=({"key": "viewer-k", "role": "viewer"},),
    )
    server, port = _start_server(config)
    try:
        h = {"X-Api-Key": "viewer-k"}
        assert _request(port, path="/health", headers=h)[0] == 200
        assert _request(port, path="/v0/summary", headers=h)[0] == 200
    finally:
        server.shutdown()


def test_multi_key_viewer_forbidden_step_export_admin() -> None:
    """Viewer key gets 403 for POST /v0/step, GET /v0/export, GET /admin/*."""
    get_abuse_counters().reset()
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_MULTI_KEY,
        key_registry=({"key": "viewer-k", "role": "viewer"},),
    )
    server, port = _start_server(config)
    try:
        h = {"X-Api-Key": "viewer-k"}
        if sys.platform != "win32":
            status, _, raw = _request_post(port, "/v0/step", b"{}", h)
            assert status == 403
            assert json.loads(raw.decode("utf-8")).get("code") == "forbidden"
        status, _, raw = _request(port, path="/v0/export", headers=h)
        assert status == 403
        status, _, raw = _request(port, path="/admin/status", headers=h)
        assert status == 403
        assert get_abuse_counters().snapshot()["forbidden"] >= 1
    finally:
        server.shutdown()


def test_multi_key_runner_can_step_not_export_admin() -> None:
    """Runner key can POST /v0/step and GET /health, /v0/summary; 403 for /v0/export, /admin/*."""
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_MULTI_KEY,
        key_registry=({"key": "runner-k", "role": "runner"},),
    )
    server, port = _start_server(config)
    try:
        h = {"X-Api-Key": "runner-k"}
        assert _request(port, path="/health", headers=h)[0] == 200
        assert _request(port, path="/v0/summary", headers=h)[0] == 200
        if sys.platform != "win32":
            status, _, _ = _request_post(port, "/v0/step", b"{}", h)
            assert status == 501
        assert _request(port, path="/v0/export", headers=h)[0] == 403
        assert _request(port, path="/admin/status", headers=h)[0] == 403
    finally:
        server.shutdown()


def test_multi_key_admin_can_all() -> None:
    """Admin key can access all endpoints."""
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_MULTI_KEY,
        key_registry=({"key": "admin-k", "role": "admin"},),
    )
    server, port = _start_server(config)
    try:
        h = {"X-Api-Key": "admin-k"}
        assert _request(port, path="/health", headers=h)[0] == 200
        assert _request(port, path="/v0/summary", headers=h)[0] == 200
        assert _request(port, path="/v0/export", headers=h)[0] == 200
        assert _request(port, path="/admin/status", headers=h)[0] == 200
        if sys.platform != "win32":
            status, _, _ = _request_post(port, "/v0/step", b"{}", h)
            assert status == 501
    finally:
        server.shutdown()


def test_forbidden_logs_request_id() -> None:
    """On 403, SECURITY_ALERT is emitted with request_id; response has X-Request-Id."""
    get_abuse_counters().reset()
    config = OnlineConfig(
        api_key=None,
        rate_limit_rps_per_key=10.0,
        rate_limit_rps_per_ip=10.0,
        max_body_bytes=1024 * 1024,
        max_inflight=10,
        host="127.0.0.1",
        port=0,
        auth_mode=AUTH_MULTI_KEY,
        key_registry=({"key": "viewer-k", "role": "viewer"},),
    )
    server, port = _start_server(config)
    try:
        status, headers, raw = _request(port, path="/admin/status", headers={"X-Api-Key": "viewer-k"})
        assert status == 403
        assert headers.get("X-Request-Id") or headers.get("x-request-id")
        assert get_abuse_counters().snapshot()["forbidden"] >= 1
    finally:
        server.shutdown()
