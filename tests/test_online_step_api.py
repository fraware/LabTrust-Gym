"""
Tests for POST /v0/step: deterministic mode, create run, step once, assert receipts and gates.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import Any

import pytest

from labtrust_gym.online.config import AUTH_OFF, OnlineConfig
from labtrust_gym.online.server import create_server


def _start_server(config: OnlineConfig) -> tuple[Any, int]:
    """Start server in daemon thread; return (server, port)."""
    server = create_server(config)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)
    return server, port


def _post_step(port: int, body: dict[str, Any]) -> tuple[int, bytes]:
    """POST /v0/step with JSON body; return (status_code, response_body)."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v0/step",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_step_deterministic_create_run_step_once() -> None:
    """
    Deterministic mode: create run via POST /v0/step, step once with NOOP.
    Assert 200, response has receipts (hashchain, emits) and gate_outcomes (status).
    """
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
        run_id = "test-run-" + str(id(config))
        body = {
            "run_id": run_id,
            "action": {
                "action_type": "NOOP",
                "args": {},
                "agent_id": "A_RECEPTION",
                "t_s": 0,
            },
        }
        status, raw = _post_step(port, body)
        assert status == 200, f"Expected 200, got {status}: {raw!r}"
        data = json.loads(raw.decode("utf-8"))
        assert "observation" in data
        assert "receipts" in data
        receipts = data["receipts"]
        assert "hashchain" in receipts
        assert "emits" in receipts
        assert "gate_outcomes" in data
        gate = data["gate_outcomes"]
        assert "status" in gate
        assert gate["status"] in ("ACCEPTED", "BLOCKED")
        assert "digests" in data
        digests = data["digests"]
        assert "head_hash" in digests
        assert "length" in digests
    finally:
        server.shutdown()


def test_step_bad_request_missing_run_id() -> None:
    """POST /v0/step without run_id returns 400."""
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
        status, raw = _post_step(port, {"action": {"action_type": "NOOP"}})
        assert status == 400
        data = json.loads(raw.decode("utf-8"))
        assert data.get("code") == "bad_request"
    finally:
        server.shutdown()


def test_step_no_501() -> None:
    """Ensure /v0/step never returns 501 Not Implemented."""
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
        status, _ = _post_step(port, {"run_id": "no-501", "action": {"action_type": "NOOP"}})
        assert status != 501, "POST /v0/step must not return 501"
    finally:
        server.shutdown()
