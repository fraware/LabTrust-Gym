# Online serve mode

The **labtrust serve** command starts a local HTTP API for evaluation or integration. It is optional; all offline commands (run-benchmark, run-study, export-receipts, etc.) are unchanged.

## Purpose

- Expose a small HTTP API (e.g. health, future step/action endpoints) for online or scripted clients.
- Default: **local-only** binding (`127.0.0.1`) and **no API key** required; suitable for development.
- When deploying in a shared or public context, configure an API key and tune rate/body/concurrency limits (see [Security controls for online mode](security_online.md)).

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
| `/v0/step` | POST | Placeholder for future step/action API; currently returns 501 Not Implemented. |

All endpoints are subject to the same abuse controls: optional API key, per-key and per-IP rate limits, request body size limit, and concurrency limit.

## Dependencies

Serve mode uses only the Python standard library (no extra pip install). Optional extras are documented in [Security controls for online mode](security_online.md).

## See also

- [Security controls for online mode](security_online.md) – API key, rate limits, body size, concurrency, telemetry.
- [Threat model](threat_model.md) – Overall threat assumptions.
