# Output controls (B009)

This document describes how to limit output over-exposure for online endpoints and public artifacts: summary views by default, role-based access to full logs, and obfuscation options. Same pipeline is used for B003 (public release) and B009 (online endpoints).

## Design principle

**Strong default: least data returned.** High-fidelity export (raw episode logs, full receipts, unredacted identifiers) requires explicit admin role or explicit flags.

## Online endpoints

### Summary view by default

- **GET /v0/summary** returns a **summary view** only: aggregated metrics, violation counts, blocked counts. No raw episode log entries, no full prompts, no raw signatures.
- Payload shape: `{ "summary": { "n_episodes", "throughput_mean", "violations_total", "blocked_count", "blocked_by_reason_code", "violations_by_invariant_id", "steps_total", ... } }`.
- Available to **viewer** role (and above). Safe for leaderboards and run summaries.

### Full logs and receipts: admin only

- **GET /v0/episode-log** returns raw episode log entries. **Requires admin role.** Viewer and runner receive **403 Forbidden**.
- **GET /v0/export** (and future artifact export endpoints) are **admin-only** (B007).
- When returning full logs or receipts to admin, use the same redaction/shaping pipeline so that configurable obfuscation (specimen IDs, work IDs, raw signatures) can be applied consistently.

## Obfuscation options

The central module `labtrust_gym.security.output_shaping` provides:

| Option | Description | Use case |
|--------|-------------|----------|
| **Specimen / work IDs** | `obfuscate_identifier(id, mode="hash" \| "truncate")` | Hash (e.g. SHA-256 prefix) or truncate for public or summary output. |
| **Signatures** | `shape_signature_verification(sv, keep_raw=False)` | By default keep only `passed`, `reason_code`, `key_id`; drop raw signature bytes. |
| **LLM fidelity** | `shape_llm_decision(llm, full_fidelity=False)` | By default return only `prompt_sha256`, `response_sha256`, `backend_id`, `model_id`, `latency_ms`, `error_code`; no full prompt or response text. |

These can be wired to policy or environment (e.g. `LABTRUST_OBFUSCATE_SPECIMEN_IDS=1`) for public or shared environments.

## Forbidden fields in summary

The following must **not** appear in viewer-facing or public summary output (enforced by `summary_contains_no_forbidden_fields` and by building summaries explicitly):

- Raw **signature**, **prompt**, **raw_prompt**, **raw_response**, **response**
- **api_key**, **secret**, **password**, **token**, **private_key**
- **episode_log** / **entries** (raw log entries; use aggregates only)

## Building a run summary

- **build_run_summary(results_or_episodes)**  
  Input: results dict with `episodes` (each with `metrics`) or a list of episode dicts.  
  Output: single dict with `n_episodes`, `throughput_mean`, `violations_total`, `blocked_count`, `blocked_by_reason_code`, `violations_by_invariant_id`, optional means for turnaround and on-time rate. Safe to expose to viewers.

- **summary_contains_no_forbidden_fields(summary)**  
  Returns `(True, [])` if the summary is safe; `(False, [list of forbidden keys found])` otherwise. Use in tests or before sending response.

## Safely exposing leaderboards and run summaries

1. **Use GET /v0/summary** for dashboards and leaderboards; do not expose GET /v0/episode-log or export URLs to viewers.
2. **Auth**: Enable B007 auth (e.g. `multi_key`) and assign **viewer** keys for read-only dashboard consumers; **admin** keys only for operators who need exports and raw logs.
3. **Obfuscation**: For public leaderboards (e.g. published results), use `build_run_summary` and optionally obfuscate task/baseline identifiers via `obfuscate_identifier` if policy requires.
4. **B003 public release** (when implemented): For package-release or ui-export in public mode, use the same `output_shaping` and redaction pipeline so that one central module governs what is allowed in public artifacts.

## Tests

- **tests/test_output_shaping.py**: Viewer cannot fetch raw episode logs (403 for GET /v0/episode-log); admin can (200 with entries); summaries contain no forbidden fields; GET /v0/summary returns summary view; obfuscation and shape helpers behave as documented.

## See also

- [Security controls for online mode](security_online.md) – B007 auth, roles, rate limits.
- [Deployment hardening](deployment_hardening.md) – B008 secrets, filesystem, artifacts.
