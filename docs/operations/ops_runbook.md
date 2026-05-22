# Operator runbook

Minimal runbook for running the LabTrust-Gym online service and handling common operations.

## Running the service

- Run `labtrust serve` from the repo root or with `LABTRUST_REPO_ROOT` set.
- Set the listen address with `--host` and `--port` (default `0.0.0.0:8765`). Bind to `127.0.0.1` for local-only access.
- Require an API key by setting `LABTRUST_ONLINE_API_KEY`; clients send `X-API-Key`. Development deployments may omit the variable when API keys are unnecessary.
- Configure rate limits with `--rate-limit-rps-per-key` and `--rate-limit-rps-per-ip`, and set maximum body size with `--max-body-bytes`.

## Key rotation and registry updates

- Rotate the API key by changing `LABTRUST_ONLINE_API_KEY`, restarting the process, and notifying clients of the new value.
- When a key registry is in use, update `policy/keys` or the configured registry path and restart so the server reloads allowed keys.

## Logging and audit retention

- Logs go to stderr by default. Redirect for retention: `labtrust serve >> /var/log/labtrust/serve.log 2>&1`.
- Abuse counters and SECURITY_ALERT emits are in-process; for audit retention, ship logs to a SIEM or append to an audit file from the process environment.

## Incident response

If you suspect abuse or an incident:

1. Collect episode logs from run directories, any evidence bundles (`EvidenceBundle.v0.1`), and the current release manifest (`RELEASE_MANIFEST.v0.1.json`) when the service is tied to a release.
2. Preserve copies of logs and bundle directories before rotation or restart.
3. Run `labtrust verify-bundle` on evidence bundles and `labtrust verify-release` on the release directory to confirm integrity.
4. Escalate through your organization’s incident process; the artifacts above support forensics and transparency.
