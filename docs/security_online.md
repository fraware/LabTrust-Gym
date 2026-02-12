# Security controls for online mode (B004, B007)

This document describes the safeguards added to **labtrust serve** (and any future online endpoints): request-level protections, response hygiene, abuse telemetry, and **B007 user/admin access control**.

## Scope

- **Online mode only**: Offline commands (run-benchmark, run-study, export-receipts, etc.) are unaffected.
- **Explicit**: Public/restrictive behaviour is enabled by configuration; default remains local-only and permissive when auth is off.

---

## B007 Authentication and authorization

### Authentication modes

| Mode | Description | When to use |
|------|-------------|-------------|
| `off` | No authentication. All endpoints are reachable without a key. | Local development only. |
| `api_key` | Single shared key. Valid key is treated as **admin**. | Simple deployments with one key. |
| `multi_key` | Key registry file; each key has a role: `admin`, `runner`, or `viewer`. | Production with least-privilege roles. |

### Configuration (B007)

| Variable | Meaning | Default |
|----------|---------|---------|
| `LABTRUST_AUTH_MODE` | `off` \| `api_key` \| `multi_key` | `off` (or `api_key` if `LABTRUST_ONLINE_API_KEY` / `LABTRUST_AUTH_KEY` set) |
| `LABTRUST_AUTH_KEY` | Single API key for `api_key` mode. | Not set |
| `LABTRUST_AUTH_KEY_FILE` | Path to YAML key registry for `multi_key` mode. | Not set |
| `LABTRUST_ONLINE_API_KEY` | Legacy; same effect as `LABTRUST_AUTH_KEY` when `LABTRUST_AUTH_MODE` is not set. | Not set |

**Key registry format** (`multi_key`): YAML file with a list of keys and roles:

```yaml
auth_keys:
  - key: "<secret-key-1>"
    role: admin
  - key: "<secret-key-2>"
    role: runner
  - key: "<secret-key-3>"
    role: viewer
```

Valid roles: `admin`, `runner`, `viewer`. Keys are matched exactly; role is case-insensitive.

### Authorization (roles)

| Role | Allowed |
|------|--------|
| **viewer** | GET `/health`, GET `/`, GET `/v0/summary` (public summaries only). |
| **runner** | Viewer + POST `/v0/step` (run tasks), limited summaries. |
| **admin** | Runner + GET `/v0/export`, GET `/v0/episode-log`, GET `/admin/*` (export artifacts, full episode logs). |

When auth is enabled, unknown paths require at least **viewer**. Insufficient privilege returns **403 Forbidden** with body `{"error": "Forbidden", "code": "forbidden"}`.

### Setup examples

**Local development (no auth):**

```bash
# Default: no key, auth off
labtrust serve
```

**Single key (admin only):**

```bash
export LABTRUST_AUTH_MODE=api_key
export LABTRUST_AUTH_KEY=your-secret-key
labtrust serve
```

**Multi-key with roles (production-style):**

```bash
export LABTRUST_AUTH_MODE=multi_key
export LABTRUST_AUTH_KEY_FILE=/path/to/auth_keys.yaml
labtrust serve
```

**Key in request:** header `X-Api-Key: <key>` or query parameter `api_key=<key>`.

### Security logging (B007)

- **SECURITY_ALERT** is emitted on auth failure (401) and authorization failure (403). No user/key details are logged; only reason code and correlation id.
- **Request correlation:** Every response includes header **X-Request-Id** (unique per request). Security events include `request_id` in the log line for correlation.

Example log line (auth failure):

```json
{"event": "SECURITY_ALERT", "reason_code": "ONLINE_AUTH_FAILURE", "request_id": "a1b2c3d4e5f6"}
```

Example (forbidden):

```json
{"event": "SECURITY_ALERT", "reason_code": "ONLINE_FORBIDDEN", "request_id": "a1b2c3d4e5f6"}
```

---

## Request-level protections (B004)

| Control | Description | Config |
|---------|-------------|--------|
| **API key / auth** | When auth enabled, requests must supply a valid key (and have sufficient role). | `LABTRUST_AUTH_MODE`, `LABTRUST_AUTH_KEY`, `LABTRUST_AUTH_KEY_FILE` |
| **Per-key rate limit** | Token-bucket rate limit per API key. | `LABTRUST_RATE_LIMIT_RPS_PER_KEY` (default 2) |
| **Per-IP rate limit** | Token-bucket rate limit per client IP. | `LABTRUST_RATE_LIMIT_RPS_PER_IP` (default 5) |
| **Request body size** | Reject requests whose `Content-Length` exceeds the limit. | `LABTRUST_MAX_BODY_BYTES` (default 262144) |
| **Concurrency** | Max number of requests in flight; excess receive 503. | `LABTRUST_MAX_INFLIGHT` (default 4) |

All limits apply even when auth is off. Default binding is `127.0.0.1` (local-only).

### Environment variables (safe defaults)

| Variable | Meaning | Default |
|----------|---------|---------|
| `LABTRUST_AUTH_MODE` | Auth mode: `off`, `api_key`, `multi_key`. | `off` |
| `LABTRUST_AUTH_KEY` | Single key for `api_key` mode. | Not set |
| `LABTRUST_AUTH_KEY_FILE` | Path to key registry YAML for `multi_key`. | Not set |
| `LABTRUST_ONLINE_API_KEY` | Legacy single key (backward compat). | Not set |
| `LABTRUST_RATE_LIMIT_RPS_PER_KEY` | Tokens per second per API key. | 2 |
| `LABTRUST_RATE_LIMIT_RPS_PER_IP` | Tokens per second per client IP. | 5 |
| `LABTRUST_MAX_BODY_BYTES` | Max request body size in bytes. | 262144 |
| `LABTRUST_MAX_INFLIGHT` | Max concurrent requests. | 4 |
| `LABTRUST_SERVE_HOST` | Bind address. | 127.0.0.1 |
| `LABTRUST_SERVE_PORT` | Port. | 8765 |

## LLM call throttling (circuit breaker and rate limit)

When the pipeline is **llm_live**, the LLM agent applies a **circuit breaker** and **rate limiter** so repeated blocks (pre-LLM or shield) do not hammer the API:

- **Circuit breaker:** After `LABTRUST_CIRCUIT_BREAKER_THRESHOLD` consecutive blocks (default 5), the agent skips LLM calls for the next `LABTRUST_CIRCUIT_BREAKER_COOLDOWN` steps (default 10), returning NOOP with reason code `CIRCUIT_BREAKER_OPEN`.
- **Rate limiter:** At most `LABTRUST_RATE_LIMIT_MAX_CALLS` LLM calls per `LABTRUST_RATE_LIMIT_WINDOW_SECONDS` seconds (default 60 per 60 s). Excess calls return NOOP with reason code `RATE_LIMITED`.

These apply only when `get_pipeline_mode() == "llm_live"`. Implemented in `src/labtrust_gym/baselines/llm/throttle.py` and wired in `LLMAgentWithShield`.

| Variable | Meaning | Default |
|----------|---------|--------|
| `LABTRUST_CIRCUIT_BREAKER_THRESHOLD` | Consecutive blocks before opening circuit. | 5 |
| `LABTRUST_CIRCUIT_BREAKER_COOLDOWN` | Steps to skip LLM after circuit opens. | 10 |
| `LABTRUST_RATE_LIMIT_MAX_CALLS` | Max LLM calls per window. | 60 |
| `LABTRUST_RATE_LIMIT_WINDOW_SECONDS` | Sliding window in seconds. | 60.0 |

## Response-level protections

- **Consistent error payloads**: Errors return JSON with `error` and `code` only; no stack traces or internal paths.
- **No info leaks**: 401/403/429/413/500 messages are generic.
- **X-Request-Id**: Every response includes a correlation id for logging and support.

## Abuse telemetry

- **SECURITY_ALERT**: For each auth failure, forbidden (403), rate-limit hit, body-too-large, or too-many-inflight, the server emits a SECURITY_ALERT event (structured log line, JSON).
- **Reason codes**: `ONLINE_AUTH_FAILURE`, `ONLINE_FORBIDDEN`, `ONLINE_RATE_LIMIT`, `ONLINE_BODY_TOO_LARGE`, `ONLINE_TOO_MANY_INFLIGHT`.
- **Aggregate counters**: In-memory counters (auth_failures, forbidden, rate_limit_hits, body_too_large, too_many_inflight) are maintained and can be exposed via server logs or future admin endpoints.
- **request_id**: All security events include `request_id` when available for correlation.

Log format (one JSON line per event):

```json
{"event": "SECURITY_ALERT", "reason_code": "ONLINE_RATE_LIMIT", "detail": "per_ip", "request_id": "a1b2c3d4"}
```

## HTTP status behaviour

| Condition | Status | Code in body |
|-----------|--------|--------------|
| Auth required and missing/invalid key | 401 | `auth_failure` |
| Valid key but insufficient privilege | 403 | `forbidden` |
| Rate limit exceeded (per key or per IP) | 429 | `rate_limit_exceeded` |
| Request body too large | 413 | `entity_too_large` |
| Too many concurrent requests | 503 | `too_many_requests` |
| Not found | 404 | `not_found` |
| Internal error | 500 | `internal_error` (no stack trace) |

## Tests

- **tests/test_online_abuse_controls.py**: Auth (401 when key required), rate limiting (429), body size (413), concurrency (503), error format.
- **tests/test_online_authz.py**: B007 auth modes (off, api_key, multi_key), role-based access (viewer/runner/admin), X-Request-Id, SECURITY_ALERT with request_id on 401/403.

## Optional dependencies

No extra pip packages are required for serve mode; rate limiting and token buckets are implemented in the standard library. If you add a dependency (e.g. for a different rate-limit backend), gate it behind the optional extra `[online]` in `pyproject.toml`.

## See also

- [Online mode](online_mode.md) – How to run the server and endpoints.
- [Security monitoring (adversarial detection)](security_monitoring.md) – In-env adversarial input detection.
