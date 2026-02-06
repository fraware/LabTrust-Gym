"""
B009: Tests for output shaping and role-based exposure.

- Viewer role cannot fetch raw episode logs (GET /v0/episode-log -> 403).
- Admin can fetch episode-log (200, entries array).
- Summaries contain no forbidden fields; GET /v0/summary returns safe aggregates.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

from labtrust_gym.online.config import AUTH_MULTI_KEY, OnlineConfig
from labtrust_gym.online.server import create_server
from labtrust_gym.security.output_shaping import (
    FORBIDDEN_IN_SUMMARY,
    build_run_summary,
    obfuscate_identifier,
    shape_llm_decision,
    shape_signature_verification,
    summary_contains_no_forbidden_fields,
)


def _request(port: int, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    """GET path; return (status_code, parsed_json_body)."""
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else {}
    except (ConnectionError, OSError) as e:
        raise RuntimeError(f"Request failed: {e}") from e


def _start_server(config: OnlineConfig) -> tuple[object, int]:
    """Start server in daemon thread; return (server, port)."""
    server = create_server(config)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.15)
    return server, port


def test_viewer_cannot_fetch_raw_episode_logs() -> None:
    """Viewer role gets 403 for GET /v0/episode-log; only admin may access raw logs."""
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
            {"key": "admin-k", "role": "admin"},
        ),
    )
    server, port = _start_server(config)
    try:
        status, body = _request(port, "/v0/episode-log", headers={"X-Api-Key": "viewer-k"})
        assert status == 403, body
        assert body.get("code") == "forbidden"
    finally:
        server.shutdown()


def test_admin_can_fetch_episode_log() -> None:
    """Admin role gets 200 for GET /v0/episode-log with entries array."""
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
        status, body = _request(port, "/v0/episode-log", headers={"X-Api-Key": "admin-k"})
        assert status == 200
        assert "entries" in body
        assert isinstance(body["entries"], list)
    finally:
        server.shutdown()


def test_summary_contains_no_forbidden_fields() -> None:
    """build_run_summary output passes summary_contains_no_forbidden_fields."""
    episodes = [
        {
            "seed": 0,
            "metrics": {
                "throughput": 2,
                "violations_by_invariant_id": {"INV-1": 1},
                "blocked_by_reason_code": {"RBAC_ACTION_DENY": 1},
                "steps": 10,
            },
        },
    ]
    summary = build_run_summary({"task": "TaskA", "episodes": episodes})
    ok, found = summary_contains_no_forbidden_fields(summary)
    assert ok, f"Forbidden keys in summary: {found}"
    for key in summary:
        assert key.lower() not in {f.lower() for f in FORBIDDEN_IN_SUMMARY}, key


def test_summary_structure() -> None:
    """build_run_summary returns expected aggregate keys."""
    summary = build_run_summary({})
    assert "n_episodes" in summary
    assert "throughput_mean" in summary
    assert "violations_total" in summary
    assert "blocked_count" in summary
    assert summary["n_episodes"] == 0
    assert summary["throughput_mean"] == 0
    assert summary["violations_total"] == 0
    assert summary["blocked_count"] == 0

    summary2 = build_run_summary(
        {
            "task": "TaskA",
            "episodes": [
                {
                    "metrics": {
                        "throughput": 3,
                        "violations_by_invariant_id": {},
                        "blocked_by_reason_code": {},
                        "steps": 5,
                    },
                },
            ],
        }
    )
    assert summary2["n_episodes"] == 1
    assert summary2["throughput_mean"] == 3
    assert summary2["task"] == "TaskA"


def test_get_v0_summary_returns_summary_view() -> None:
    """GET /v0/summary returns JSON with 'summary' key containing safe aggregates."""
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
        status, body = _request(port, "/v0/summary", headers={"X-Api-Key": "viewer-k"})
        assert status == 200
        assert "summary" in body
        summary = body["summary"]
        ok, found = summary_contains_no_forbidden_fields(summary)
        assert ok, f"Forbidden keys in summary: {found}"
        assert "n_episodes" in summary
        assert "violations_total" in summary
        assert "blocked_count" in summary
    finally:
        server.shutdown()


def test_obfuscate_identifier() -> None:
    """Hash and truncate modes produce obfuscated identifiers."""
    val = "specimen-S1-abc"
    hashed = obfuscate_identifier(val, mode="hash")
    assert hashed != val
    assert len(hashed) == 16
    assert all(c in "0123456789abcdef" for c in hashed)
    truncated = obfuscate_identifier(val, mode="truncate", truncate_len=4)
    assert truncated == "spec..."
    assert obfuscate_identifier("ab", mode="truncate", truncate_len=4) == "ab"


def test_shape_signature_verification_strips_raw() -> None:
    """shape_signature_verification(keep_raw=False) returns only passed, reason_code, key_id."""
    sv = {
        "passed": True,
        "reason_code": None,
        "key_id": "k1",
        "signature": "base64raw...",
    }
    out = shape_signature_verification(sv, keep_raw=False)
    assert out.get("passed") is True
    assert out.get("key_id") == "k1"
    assert "signature" not in out


def test_shape_llm_decision_reduces_fidelity() -> None:
    """full_fidelity=False returns hashes and metadata only."""
    llm = {
        "prompt_sha256": "abc",
        "response_sha256": "def",
        "backend_id": "openai",
        "raw_prompt": "full prompt text",
        "raw_response": "full response",
    }
    out = shape_llm_decision(llm, full_fidelity=False)
    assert out.get("prompt_sha256") == "abc"
    assert out.get("response_sha256") == "def"
    assert out.get("backend_id") == "openai"
    assert "raw_prompt" not in out
    assert "raw_response" not in out
