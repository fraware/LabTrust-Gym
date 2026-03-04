# Security monitoring: adversarial input detection

This document describes the **adversarial input detector**: a defensive monitoring layer that flags suspicious text in observations and LLM inputs, emits **SECURITY_ALERT** and **SECURITY_EVENT**, and ties into reason codes and evidence.

## Purpose

- **Defensive monitoring only**: Detect patterns that may indicate prompt injection, jailbreak attempts, or suspected exfiltration. No offensive guidance; no external calls.
- **Deterministic and bounded**: Keyword/pattern-based, configurable via policy; inputs truncated to a max length.
- **Audit trail**: Detection results flow into episode logs, receipts, and ui-export (reason_codes + events).

## Signal sources

The detector consumes:

1. **Raw text from observations**: `specimen_notes`, `scenario_notes` (and optional `notes`, `metadata_notes`). These are the same untrusted fields that feed the LLM context (see `baselines.llm.context_builder`).
2. **LLM input messages**: Optional `llm_messages` (list of dict/str) when the step used an LLM agent.
3. **LLM output text**: Optional `llm_output_text` (e.g. rationale or raw response) for injection-style patterns in model output.

Observation context is passed per step by the PettingZoo env: it builds a dict from the previous step’s observations and from action_infos (e.g. `_llm_decision`). When severity is at or above the configured threshold, the env augments the step result with **SECURITY_ALERT** and **SECURITY_EVENT**.

## Policy configuration

- **File**: `policy/security/adversarial_detection.v0.1.yaml`
- **Schema**: `policy/schemas/adversarial_detection.v0.1.schema.json`
- **Validation**: `labtrust validate-policy` includes this file.

### Main knobs

| Field | Meaning |
|-------|--------|
| `severity_threshold` | Emit SECURITY_ALERT when detector severity >= this (0–3). Default 1. |
| `max_text_length` | Truncate each text field to this many characters (bounded scan). |
| `normalize_before_match` | When true, apply allowlisted normalizers to text before pattern match (evasion hardening: ZWSP/homoglyphs/base64). |
| `normalizers` | Allowlist: `strip_format_chars`, `nfkc`, `collapse_whitespace`, `decode_base64_scan`. Only these are applied; behaviour is auditable. |
| `max_decoded_base64_len` | Cap on decoded base64 length when `decode_base64_scan` is in normalizers (default 2000). |
| `patterns` | List of `{ id, pattern, severity, reason_code }`. `pattern` is a substring (case-insensitive) or regex (prefix `re:`). |
| `suggested_actions` | Map severity 0–3 to suggested response: NOOP, THROTTLE_AGENT, REQUIRE_HUMAN_REVIEW, FREEZE_EPISODE. |

**Auditability:** Pattern-only detection remains the primary, auditable control. The optional classifier (`use_classifier`) is supplementary and best-effort; it must not replace pattern-based blocking for critical severity. When the classifier is unavailable, detection falls back to pattern-only (see Prompt-injection defense doc for block_severity_threshold and classifier fallback).

### Tuning thresholds

- **Reduce false positives**: Raise `severity_threshold` (e.g. 2) so only higher-severity patterns trigger alerts; or remove/relax patterns that fire on benign text.
- **Increase sensitivity**: Lower `severity_threshold` to 0 or add more patterns; be aware of false positives in normal notes.
- **Bounded load**: Keep `max_text_length` moderate (e.g. 2000); larger values increase scan cost and risk of abuse.

## Reason codes and emits

- **Reason codes** (in `policy/reason_codes/reason_code_registry.v0.1.yaml`): **ADV_INJECTION_DETECTED**, **ADV_JAILBREAK_PATTERN**, **ADV_SUSPECTED_EXFIL**. Used in `security_event.reason_code` and can drive enforcement.
- **Emits** (in `policy/emits/emits_vocab.v0.1.yaml`): **SECURITY_ALERT**, **SECURITY_EVENT**. Emitted when severity >= threshold; SECURITY_EVENT carries the structured payload.

## Episode log and evidence bundle

- **Episode log**: Each step entry may include **security_event** when the detector fired: `detection_flags`, `severity`, `suggested_action`, `reason_code`, `matched_pattern_ids`.
- **Evidence bundle**: Receipts and invariant/eval trace include step data; security_event is part of the step payload and thus appears in the exported episode log subset and related traces.
- **ui-export**: Reason codes and events are included in the UI bundle; SECURITY_ALERT and security_event show up in the event stream and reason_codes registry.

## Enforcement integration

The detector returns a **suggested_action** (NOOP, THROTTLE_AGENT, REQUIRE_HUMAN_REVIEW, FREEZE_EPISODE). Optional enforcement (throttle / freeze) can be wired to existing enforcement mechanisms (e.g. `policy/enforcement/enforcement_map.v0.1.yaml`) by matching on a synthetic “security” invariant or by handling SECURITY_ALERT in the runner. Current behaviour: SECURITY_ALERT and SECURITY_EVENT are emitted and recorded; automatic throttle/freeze is not applied by default.

## Prompt-injection defense (layered)

A separate **prompt-injection defense** layer (`policy/security/prompt_injection_defense.v0.1.yaml`) adds pre-LLM blocking, optional sanitization, and output-consistency checks. When the detector severity is at or above `block_severity_threshold`, the LLM call is skipped and the agent returns NOOP with `PROMPT_INJECTION_DETECTED`. See [Prompt-injection defense](prompt_injection_defense.md).

## Classifier fallback and limits

When `use_classifier` is true, the detector calls an optional judge URL (`LABTRUST_CLASSIFIER_JUDGE_URL`). If the judge is unavailable (timeout, connection error, or invalid response), the detector by default **falls back to pattern-only** (fail-open). You can set **classifier_fallback_severity_when_unavailable** in `adversarial_detection.v0.1.yaml` to 1, 2, or 3 to treat judge unavailability as that severity (fail-closed): the detector will then merge that severity with pattern results so pre-LLM block can still fire. Omitted or 0 = pattern-only. Rate limiting or circuit breaking on the judge URL is not implemented in-core; operators can put a reverse proxy or rate limiter in front of the judge endpoint.

## Rate limiting and circuit breaker

- **LLM circuit breaker:** When a backend sets **last_error_code** after 429, timeout, or refusal, the LLM agent calls **circuit_breaker.record_block()**. Consecutive provider failures open the circuit so further calls are short-circuited (e.g. return NOOP with reason code). See `baselines/llm` and the guardrails section in the LLM live doc.
- **LLM rate limiter:** A shared **TokenBucket** (or equivalent) can be passed to all LLM agents when many agents share one backend; **act()** waits at most **global_rate_limit_max_wait_s** for a token. Rate-limited agents return NOOP with **AGENT_RATE_LIMIT** when the deadline is exceeded. See scale config and `scale_operational_limits.md`.
- **Judge URL rate limiting:** The classifier/judge endpoint (`LABTRUST_CLASSIFIER_JUDGE_URL`) is not rate-limited in-core. For production, put a reverse proxy or rate limiter in front of the judge, or implement an optional wrapper around the judge call with a token bucket.

## False positives

- **Clinical or operational phrases**: Patterns that match normal specimen or scenario notes (e.g. “override” in a clinical context) can trigger ADV_INJECTION_DETECTED. Tune patterns or severity_threshold, or narrow patterns to clearly adversarial substrings/regexes.
- **Regex safety**: Patterns with `re:` are compiled with `re.IGNORECASE`; avoid catastrophic backtracking by keeping regexes simple and bounded.

## Tests

- **tests/test_adversarial_detector_unit.py**: Pure unit tests (load policy, detect on specimen_notes/scenario_notes/llm_output_text, determinism, truncation).
- **tests/test_llm_prompt_injection_golden.py**: Extended so that (1) prompt-injection scenario strings produce detector flags and severity >= threshold; (2) a full env step with observation text containing injection either emits SECURITY_ALERT / security_event or skips with a note (detector contract still asserted).

Deterministic runs remain deterministic; the detector is policy-configurable and validated by `labtrust validate-policy`.
