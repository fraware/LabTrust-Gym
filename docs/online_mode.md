# Online serve mode

The **labtrust serve** command starts a local HTTP API for evaluation or integration. It is optional; all offline commands (run-benchmark, run-study, export-receipts, etc.) are unchanged.

## Purpose

- Expose a small HTTP API (health, POST /v0/step) for online or scripted clients.
- Default: **local-only** binding (`127.0.0.1`) and **no API key** required; suitable for development (deterministic mode).
- When deploying with **online_mode** (API key or `LABTRUST_API_TOKEN` set), require Bearer token or API key for protected routes. See [Security controls for online mode](security_online.md).

## Running the server

```bash
labtrust serve
```

- Binds to `127.0.0.1:8765` by default.
- Override via environment or CLI:

  | Override | Env var | CLI |
  |----------|---------|-----|
  | Host | `LABTRUST_SERVE_HOST` | `--host` |
  | Port | `LABTRUST_SERVE_PORT` | `--port` |

Example:

```bash
labtrust serve --port 9000
```

## Endpoints

| Path | Method | Description |
|------|--------|-------------|
| `/` or `/health` | GET | Health check; returns `{"status": "ok"}`. |
| `/v0/step` | POST | Execute one environment step (adapter + orchestrator). Works in deterministic mode without network. Request: run_id, action; response: observation, receipts, gate_outcomes, digests. |

All endpoints are subject to abuse controls: optional API key or Bearer token, per-key and per-IP rate limits, body size and concurrency limits.

## POST /v0/step

Executes one environment step via the default adapter (deterministic). Create a run by sending a first request with a `run_id`; subsequent requests with the same `run_id` continue the episode.

### Request body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_id` | string | Yes | Identifies the run (episode); created on first use. |
| `action` | object | Yes | Event to apply: `action_type`, `args`, `agent_id`, `t_s`, optional `reason_code`, `token_refs`, `key_id`, `signature`. |
| `tool_payload` | object | No | Optional tool payload. |
| `flags` | object | No | Optional flags. |

### Response (200)

| Field | Type | Description |
|-------|------|-------------|
| `observation` | object | State snapshot or step summary. |
| `receipts` | object | `hashchain` (head_hash, length, last_event_hash), `emits` (list), `token_consumed` (list). |
| `gate_outcomes` | object | `status` ("ACCEPTED" \| "BLOCKED"), `violations`, `blocked_reason_code`. |
| `digests` | object | `head_hash`, `length`, `last_event_hash`. |

### Example (deterministic, no auth)

```bash
curl -s -X POST http://127.0.0.1:8765/v0/step \
  -H "Content-Type: application/json" \
  -d '{"run_id": "my-run-1", "action": {"action_type": "NOOP", "args": {}, "agent_id": "A_RECEPTION", "t_s": 0}}'
```

Example response:

```json
{
  "observation": {"step": 0, "event_id": "e0"},
  "receipts": {
    "hashchain": {"head_hash": "...", "length": 1, "last_event_hash": "..."},
    "emits": [],
    "token_consumed": []
  },
  "gate_outcomes": {"status": "ACCEPTED", "violations": [], "blocked_reason_code": null},
  "digests": {"head_hash": "...", "length": 1, "last_event_hash": "..."}
}
```

When the server runs with **online_mode** (e.g. `LABTRUST_API_TOKEN` set), send the Bearer token: `Authorization: Bearer <token>`.

## Dependencies

Serve mode uses only the Python standard library (no extra pip install). Optional extras are documented in [Security controls for online mode](security_online.md).

## See also

- [Security controls for online mode](security_online.md) – API key, rate limits, body size, concurrency, telemetry.
- [Threat model](threat_model.md) – Overall threat assumptions.
