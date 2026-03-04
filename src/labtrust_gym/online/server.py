"""
HTTP server for the labtrust serve command.

Handles request/response with optional API key or Bearer token; when online
mode is enabled, a token is required. Enforces per-key and per-IP rate limits,
body size and concurrency limits. POST /v0/step runs one environment step via
the adapter (works in deterministic mode without network). Emits security
telemetry for auth failures, rate limits, and abuse.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from typing import TYPE_CHECKING, Any, cast

from labtrust_gym.online.authz import has_privilege, required_role_for_path
from labtrust_gym.online.config import OnlineConfig, resolve_role
from labtrust_gym.online.rate_limit import KeyedTokenBuckets
from labtrust_gym.online.telemetry import (
    ONLINE_AUTH_FAILURE,
    ONLINE_BODY_TOO_LARGE,
    ONLINE_FORBIDDEN,
    ONLINE_RATE_LIMIT,
    ONLINE_TOO_MANY_INFLIGHT,
    emit_security_alert,
    get_abuse_counters,
)
from labtrust_gym.runner import get_default_env_adapter
from labtrust_gym.runner.adapter import LabTrustEnvAdapter
from labtrust_gym.security.output_shaping import build_run_summary

if TYPE_CHECKING:
    from typing import Protocol

    from labtrust_gym.online.telemetry import AbuseCounters

    class _LabTrustServerProto(Protocol):
        labtrust_config: OnlineConfig
        labtrust_limiters_per_key: KeyedTokenBuckets
        labtrust_limiters_per_ip: KeyedTokenBuckets
        labtrust_inflight_semaphore: threading.Semaphore
        labtrust_abuse_counters: AbuseCounters


# -----------------------------
# Step API request/response models
# -----------------------------
@dataclass
class StepRequest:
    """POST /v0/step request body."""

    run_id: str
    action: dict[str, Any]
    tool_payload: dict[str, Any] | None = None
    flags: dict[str, Any] | None = None


@dataclass
class StepResponse:
    """POST /v0/step response body."""

    observation: dict[str, Any]
    receipts: dict[str, Any]
    gate_outcomes: dict[str, Any]
    digests: dict[str, Any]


def _default_initial_state() -> dict[str, Any]:
    """Minimal initial state for a new run (deterministic)."""
    return {
        "system": {"now_s": 0, "downtime_active": False},
        "agents": [
            {"agent_id": "A_RECEPTION", "zone_id": "Z_SRA_RECEPTION"},
        ],
        "specimens": [],
        "tokens": [],
        "timing_mode": "explicit",
    }


# Run store: run_id -> { adapter, step_count, rng_seed }
_run_store: dict[str, dict[str, Any]] = {}
_run_store_lock = threading.Lock()


def _get_or_create_run(run_id: str) -> tuple[LabTrustEnvAdapter, int]:
    """Get or create run; returns (adapter, step_count)."""
    with _run_store_lock:
        if run_id in _run_store:
            r = _run_store[run_id]
            return r["adapter"], r["step_count"]
        adapter = get_default_env_adapter()
        initial_state = _default_initial_state()
        adapter.reset(
            initial_state,
            deterministic=True,
            rng_seed=42,
        )
        _run_store[run_id] = {
            "adapter": adapter,
            "step_count": 0,
            "rng_seed": 42,
        }
        return adapter, 0


def _increment_run_step(run_id: str) -> None:
    with _run_store_lock:
        if run_id in _run_store:
            _run_store[run_id]["step_count"] += 1


def _handle_step(body: dict[str, Any]) -> StepResponse:
    """Execute one step; returns response model."""
    run_id = str(body.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run_id is required")
    action = body.get("action")
    if not isinstance(action, dict):
        raise ValueError("action must be an object")
    adapter, step_count = _get_or_create_run(run_id)
    t_s = int(action.get("t_s", 0)) if action.get("t_s") is not None else step_count * 10
    event_id = f"e{step_count}"
    event = {
        "event_id": event_id,
        "t_s": t_s,
        "agent_id": str(action.get("agent_id", "A_RECEPTION")),
        "action_type": str(action.get("action_type", "NOOP")),
        "args": action.get("args") if isinstance(action.get("args"), dict) else {},
        "reason_code": action.get("reason_code"),
        "token_refs": action.get("token_refs") if isinstance(action.get("token_refs"), list) else [],
    }
    if action.get("key_id") is not None:
        event["key_id"] = action["key_id"]
    if action.get("signature") is not None:
        event["signature"] = action["signature"]
    result = adapter.step(event)
    _increment_run_step(run_id)
    status = result.get("status", "ACCEPTED")
    hashchain = result.get("hashchain") or {}
    emits = result.get("emits") or []
    violations = result.get("violations") or []
    observation = (
        result.get("state_snapshot")
        if isinstance(result.get("state_snapshot"), dict)
        else {"step": step_count, "event_id": event_id}
    )
    receipts = {
        "hashchain": hashchain,
        "emits": emits,
        "token_consumed": result.get("token_consumed") or [],
    }
    gate_outcomes = {
        "status": status,
        "violations": violations,
        "blocked_reason_code": result.get("blocked_reason_code"),
    }
    digests = {
        "head_hash": hashchain.get("head_hash"),
        "length": hashchain.get("length"),
        "last_event_hash": hashchain.get("last_event_hash"),
    }
    return StepResponse(
        observation=observation,
        receipts=receipts,
        gate_outcomes=gate_outcomes,
        digests=digests,
    )


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    """Client IP from request (no forwarding headers to avoid spoofing in default setup)."""
    return handler.client_address[0] if handler.client_address else "0.0.0.0"


def _extract_api_key(handler: BaseHTTPRequestHandler) -> str | None:
    """API key from X-API-Key header or query param api_key."""
    key = handler.headers.get("X-Api-Key") or handler.headers.get("x-api-key")
    if key:
        return key.strip() or None
    # Query string: parse manually to avoid exposing full path
    path = handler.path
    if "?" in path:
        qs = path.split("?", 1)[1]
        for part in qs.split("&"):
            if part.startswith("api_key="):
                return part[8:].strip() or None
    return None


def _extract_bearer_token(handler: BaseHTTPRequestHandler) -> str | None:
    """Bearer token from Authorization header."""
    auth = handler.headers.get("Authorization") or handler.headers.get("authorization")
    if not auth or not auth.strip().lower().startswith("bearer "):
        return None
    return auth[7:].strip() or None


def _send_json(handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
    """Send JSON response with consistent headers and X-Request-Id (B007)."""
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    req_id = getattr(handler, "_request_id", None) or ""
    if req_id:
        handler.send_header("X-Request-Id", req_id)
    handler.end_headers()
    handler.wfile.write(payload)
    handler.wfile.flush()


def _send_error(handler: BaseHTTPRequestHandler, status: int, code: str, message: str) -> None:
    """Send a consistent error response (no internal details)."""
    _send_json(handler, status, {"error": message, "code": code})


class LabTrustHTTPRequestHandler(BaseHTTPRequestHandler):
    """Handler that applies auth, rate limits, body size, concurrency; then delegates."""

    # Injected by our server: config, limiters, semaphore
    config: OnlineConfig
    limiters_per_key: KeyedTokenBuckets
    limiters_per_ip: KeyedTokenBuckets
    inflight_semaphore: threading.Semaphore
    abuse_counters: AbuseCounters
    _user_role: str | None

    def log_message(self, format: str, *args: object) -> None:
        """Log to server logger; avoid default stdout."""
        pass

    def _get_server_attrs(self) -> None:
        server = cast("_LabTrustServerProto", self.server)
        if hasattr(server, "labtrust_config"):
            self.config = server.labtrust_config
            self.limiters_per_key = server.labtrust_limiters_per_key
            self.limiters_per_ip = server.labtrust_limiters_per_ip
            self.inflight_semaphore = server.labtrust_inflight_semaphore
            self.abuse_counters = server.labtrust_abuse_counters
        else:
            raise RuntimeError("LabTrust server attributes not set")
        self._request_id = uuid.uuid4().hex
        self._user_role = None

    def _check_auth(self) -> bool:
        """Return True if auth OK; else send 401 and return False. Sets _user_role when auth required."""
        if not self.config.auth_required and self.config.api_token is None:
            return True
        key = _extract_api_key(self)
        role = resolve_role(key, self.config)
        if role is None and self.config.api_token:
            bearer = _extract_bearer_token(self)
            if bearer and bearer == self.config.api_token:
                role = "runner"
        if self.config.auth_required or self.config.api_token:
            if role is None:
                emit_security_alert(
                    ONLINE_AUTH_FAILURE,
                    counters=self.abuse_counters,
                    request_id=getattr(self, "_request_id", None),
                )
                _send_error(
                    self,
                    401,
                    "auth_failure",
                    "Invalid or missing API key or Bearer token",
                )
                return False
        self._user_role = role
        return True

    def _check_authorization(self) -> bool:
        """Return True if user_role has privilege for this method+path; else send 403 and return False."""
        if not self.config.auth_required:
            return True
        path = self.path.split("?")[0].rstrip("/") or "/"
        required = required_role_for_path(self.command, path)
        if required is None or has_privilege(self._user_role, required):
            return True
        emit_security_alert(
            ONLINE_FORBIDDEN,
            counters=self.abuse_counters,
            request_id=getattr(self, "_request_id", None),
        )
        _send_error(self, 403, "forbidden", "Forbidden")
        return False

    def _check_rate_limit(self) -> bool:
        """Return True if allowed; else send 429 and return False."""
        ip = _client_ip(self)
        key = _extract_api_key(self)
        if key and not self.limiters_per_key.allow(key):
            emit_security_alert(
                ONLINE_RATE_LIMIT,
                "per_key",
                counters=self.abuse_counters,
                request_id=getattr(self, "_request_id", None),
            )
            _send_error(self, 429, "rate_limit_exceeded", "Rate limit exceeded")
            return False
        if not self.limiters_per_ip.allow(ip):
            emit_security_alert(
                ONLINE_RATE_LIMIT,
                "per_ip",
                counters=self.abuse_counters,
                request_id=getattr(self, "_request_id", None),
            )
            _send_error(self, 429, "rate_limit_exceeded", "Rate limit exceeded")
            return False
        return True

    def _check_body_size(self) -> bool:
        """Return True if body size OK; else send 413, drain body, and return False."""
        cl = self.headers.get("Content-Length")
        if cl is None:
            return True
        try:
            n = int(cl)
        except ValueError:
            _send_error(self, 400, "bad_request", "Invalid request")
            return False
        if n > self.config.max_body_bytes:
            emit_security_alert(ONLINE_BODY_TOO_LARGE, counters=self.abuse_counters)
            _send_error(self, 413, "entity_too_large", "Request entity too large")
            # Drain body so client can finish sending and read our response
            to_read = min(n, self.config.max_body_bytes)
            if to_read > 0:
                try:
                    self.rfile.read(to_read)
                except (ConnectionError, OSError):
                    pass
            return False
        return True

    def _acquire_inflight(self) -> bool:
        """Return True if acquired; else send 503 and return False."""
        acquired = self.inflight_semaphore.acquire(blocking=False)
        if not acquired:
            emit_security_alert(
                ONLINE_TOO_MANY_INFLIGHT,
                counters=self.abuse_counters,
                request_id=getattr(self, "_request_id", None),
            )
            _send_error(self, 503, "too_many_requests", "Service temporarily unavailable")
            return False
        return True

    def _read_body_capped(self) -> bytes:
        """Read request body up to max_body_bytes."""
        cl = self.headers.get("Content-Length")
        if not cl:
            return b""
        try:
            n = min(int(cl), self.config.max_body_bytes)
        except ValueError:
            return b""
        if n <= 0:
            return b""
        return self.rfile.read(n)

    def do_GET(self) -> None:
        """GET: health, summary, export, admin; auth then authz then rate/inflight."""
        self._get_server_attrs()
        if not self._check_auth():
            return
        if not self._check_authorization():
            return
        if not self._check_rate_limit():
            return
        if not self._acquire_inflight():
            return
        try:
            path = self.path.split("?")[0].rstrip("/") or "/"
            if path in ("/health", "/"):
                _send_json(self, 200, {"status": "ok"})
            elif path == "/v0/summary":
                # B009: summary view by default (aggregated metrics, no raw logs)
                summary = build_run_summary({})
                _send_json(self, 200, {"summary": summary})
            elif path == "/v0/episode-log":
                # B009: full episode log only for admin (authz already enforced)
                _send_json(self, 200, {"entries": []})
            elif path.startswith("/v0/export"):
                _send_json(self, 200, {"export": "ok"})
            elif path.startswith("/admin/"):
                _send_json(self, 200, {"admin": "ok"})
            else:
                _send_error(self, 404, "not_found", "Not found")
        finally:
            self.inflight_semaphore.release()

    def do_POST(self) -> None:
        """POST: auth, authz, rate limit, body size, inflight; then handle."""
        self._get_server_attrs()
        if not self._check_auth():
            return
        if not self._check_authorization():
            return
        if not self._check_rate_limit():
            return
        if not self._check_body_size():
            return
        if not self._acquire_inflight():
            return
        try:
            path = self.path.split("?")[0].rstrip("/") or "/"
            if path in ("/v0/step", "/v0/step/"):
                body_bytes = self._read_body_capped()
                try:
                    body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                except (json.JSONDecodeError, UnicodeDecodeError):
                    _send_error(self, 400, "bad_request", "Invalid JSON body")
                    return
                try:
                    resp = _handle_step(body)
                    _send_json(self, 200, asdict(resp))
                except ValueError as e:
                    _send_error(self, 400, "bad_request", str(e))
            else:
                _send_error(self, 404, "not_found", "Not found")
        except Exception:
            # Do not leak stack traces
            _send_error(self, 500, "internal_error", "An error occurred")
        finally:
            self.inflight_semaphore.release()


class LabTrustHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTPServer so concurrency limit is exercised; holds config, limiters, semaphore."""

    def __init__(self, server_address: tuple[str, int], config: OnlineConfig) -> None:
        super().__init__(server_address, LabTrustHTTPRequestHandler)
        self.labtrust_config = config
        cap_key = max(1.0, 2 * config.rate_limit_rps_per_key)
        cap_ip = max(1.0, 2 * config.rate_limit_rps_per_ip)
        self.labtrust_limiters_per_key = KeyedTokenBuckets(config.rate_limit_rps_per_key, cap_key)
        self.labtrust_limiters_per_ip = KeyedTokenBuckets(config.rate_limit_rps_per_ip, cap_ip)
        self.labtrust_inflight_semaphore = threading.Semaphore(config.max_inflight)
        self.labtrust_abuse_counters = get_abuse_counters()


def create_server(config: OnlineConfig) -> LabTrustHTTPServer:
    """Create the HTTP server without starting it (for tests)."""
    return LabTrustHTTPServer((config.host, config.port), config)


def run_server(config: OnlineConfig | None = None) -> None:
    """
    Run the online HTTP server (blocking). Uses load_online_config() if config is None.
    """
    from labtrust_gym.online.config import load_online_config

    cfg = config if config is not None else load_online_config()
    server = create_server(cfg)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
