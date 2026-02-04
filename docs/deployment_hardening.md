# Deployment hardening (B008)

This document describes controls to protect the model deployment environment in online and live-LLM mode: secrets handling, filesystem boundaries, and optional artifact safety.

## Scope

- **Secrets**: Never log or print API keys; use the secret scrubber for debug output.
- **Filesystem**: All server-side writes must stay under a configurable base dir; path traversal is blocked.
- **Artifacts**: Optional encryption-at-rest is stubbed; public mode avoids writing sensitive artifacts.

## Secrets

### Secret scrubber

The module `labtrust_gym.security.secret_scrubber` provides:

- **get_secret_env_names()**: Returns environment variable names considered secret (names containing KEY, SECRET, PASSWORD, TOKEN, CREDENTIAL, AUTH).
- **scrub_secrets(text, secret_names=None, placeholder="<redacted>")**: Redacts secret values from a string (env-style `KEY=value` and JSON-style `"key": "value"`).
- **scrub_dict_for_log(d)**: Returns a copy of a dict with secret-like keys replaced by `<redacted>`; use before logging config or request context.

### Practice

- Do not log `os.environ`, raw config, or API keys.
- When logging config or error context, use `scrub_dict_for_log(config)` or `scrub_secrets(debug_string)`.
- LLM backends read API keys from the environment only; they are never printed or included in SECURITY_ALERT payloads.

## Filesystem boundaries

### LABTRUST_RUNS_DIR

When set, **LABTRUST_RUNS_DIR** is the base directory for run and artifact output. Any code that writes run logs, receipts, or evidence bundles (e.g. when the online server adds export/run endpoints) must resolve paths under this base.

- **get_runs_dir()**: Returns `Path(LABTRUST_RUNS_DIR)` if set, otherwise `Path.cwd()`.
- **resolve_within_base(base_dir, requested)**: Resolves `requested` relative to `base_dir`; returns `None` if the result would escape the base (e.g. `..`, absolute path).
- **is_safe_filename_component(name)**: Returns `False` for `..`, `.`, or names containing `/`, `\`, or null.
- **assert_under_runs_dir(path)**: Raises `ValueError` if `path` is not under `get_runs_dir()`.

### Path traversal

Disallow path traversal in any filename or path parameter received from the network or user input:

1. Validate with `is_safe_filename_component()` for single components.
2. Resolve with `resolve_within_base(get_runs_dir(), requested)` and reject if the result is `None`.

## Artifact storage

### Encryption-at-rest (stub)

- **LABTRUST_ARTIFACT_ENCRYPTION_KEY**: When set, the runtime treats artifact encryption as desired. The current implementation does **not** encrypt; artifacts are written in plaintext. This stub allows:
  - Future implementation of envelope encryption (e.g. AES with a key derived from the env value).
  - Operational policy to avoid writing sensitive artifacts when the key is not set (e.g. in public or shared environments).

- **should_encrypt_artifacts()**: Returns `True` when `LABTRUST_ARTIFACT_ENCRYPTION_KEY` is set.
- **write_artifact_safe(path, data, public_mode=False, sensitive=True)**: Writes `data` to `path`. If `public_mode` and `sensitive`, the write is skipped. Encryption is not applied in the current stub.

### Public mode

Planned B003 public-release flows (e.g. **package-release --public**, **ui-export --public**) will redact or omit sensitive fields and produce a REDACTION_REPORT.md when implemented; they will not rely on artifact encryption. Until then, use standard package-release and ui-export and control exposure via [Output controls](output_controls.md) and access control.

## Safe defaults

- **Network**: Default bind for `labtrust serve` is `127.0.0.1` (local-only).
- **Auth**: Default is off; enable via `LABTRUST_AUTH_MODE` and keys (see [Security controls for online mode](security_online.md)).
- **Logs**: No raw prompts or API keys; SECURITY_ALERT events do not include secret material.

## Tests

- **tests/test_secret_scrubber.py**: Redaction of env-style and JSON-style secrets; `scrub_dict_for_log` for nested dicts.
- **tests/test_online_fs_safety.py**: Path traversal rejected; `resolve_within_base` and `get_runs_dir()` behavior; `assert_under_runs_dir` raises when path escapes.

## See also

- [Security controls for online mode](security_online.md) – Auth, rate limits, B007.
- [Output controls](output_controls.md) – B009 summary view and role-based exposure.
