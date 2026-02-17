# Operator runbook

Minimal runbook for running the LabTrust-Gym online service and handling common operations.

## Running the service

- Start: `labtrust serve` (from repo root or with `LABTRUST_REPO_ROOT` set).
- Listen address: `--host` and `--port` (default 0.0.0.0:8765). Use 127.0.0.1 for local-only.
- Auth: set `LABTRUST_ONLINE_API_KEY` to require API key; clients send `X-API-Key`. Leave unset for no auth (dev only).
- Rate limits: configured via `--rate-limit-rps-per-key` and `--rate-limit-rps-per-ip`; body size via `--max-body-bytes`.

## Key rotation and registry updates

- API key: change `LABTRUST_ONLINE_API_KEY` and restart the process; notify clients of the new key.
- Key registry (if used): update policy/keys or the configured registry path and restart so the server reloads allowed keys.

## Logging and audit retention

- Logs go to stderr by default. Redirect for retention: `labtrust serve >> /var/log/labtrust/serve.log 2>&1`.
- Abuse counters and SECURITY_ALERT emits are in-process; for audit retention, ship logs to a SIEM or append to an audit file from the process environment.

## Incident response

If you suspect abuse or an incident:

1. Collect: episode logs (from run dirs), any evidence bundles (EvidenceBundle.v0.1), and the current release manifest (RELEASE_MANIFEST.v0.1.json) if the service is tied to a release.
2. Preserve: copy logs and bundle dirs before rotation or restart.
3. Review: run `labtrust verify-bundle` on evidence bundles and `labtrust verify-release` on the release dir to confirm integrity.
4. Escalate: use your organization’s incident process; the above artifacts support forensics and transparency.
