# Prompt-injection defense (state-of-the-art)

Layered defenses for LLM agents in hospital lab flows: pre-LLM blocking, optional sanitization, and output consistency checks. Config: `policy/security/prompt_injection_defense.v0.1.yaml`.

## Layers

1. **Pre-LLM**: Adversarial detection runs on untrusted text (from `state_summary.untrusted_notes.samples`) before the prompt is built. If severity is at or above `block_severity_threshold`, the LLM call is skipped and the agent returns NOOP with reason code `PROMPT_INJECTION_DETECTED` (no prompt is sent).
2. **Sanitization** (optional): When `sanitizer_mode` is `truncate`, untrusted text is capped at `max_untrusted_chars`. When `redact`, text that triggered detection (severity >= `sanitize_redaction_severity`) is replaced with `[UNTRUSTED_INPUT_REDACTED]` in the prompt so the model never sees the raw injection.
3. **Output consistency**: After the LLM responds, the response is checked for long verbatim substrings from untrusted samples. If the model echoed or followed untrusted content (length >= `min_verbatim_len`), the action is discarded and NOOP is returned with reason `UNTRUSTED_NOTE_AS_INSTRUCTION`.

## Policy knobs

| Field | Meaning |
|-------|--------|
| `block_severity_threshold` | Block LLM call when detector severity >= this (0–3). 0 = never block on detection; 2 = block on medium/high. |
| `block_reason_code` | Reason code when blocking (default `PROMPT_INJECTION_DETECTED`). |
| `sanitizer_mode` | `none`, `truncate`, or `redact`. |
| `max_untrusted_chars` | Cap per untrusted sample (truncate mode). |
| `sanitize_redaction_severity` | When to replace with redaction (severity >= this). |
| `output_consistency_check` | Enable post-response verbatim check. |
| `min_verbatim_len` | Minimum substring length to flag (default 20). |

## Integration

The LLM agent (`LLMAgentWithShield`) runs the pre-LLM check after building `state_summary` and before calling the backend. If the check blocks, it returns `(ACTION_NOOP, noop_action, meta)` with `_shield_filtered=True` and `_shield_reason_code=PROMPT_INJECTION_DETECTED`. The output consistency check runs after the LLM returns and before parsing the action; if it flags, the same NOOP path is taken with `UNTRUSTED_NOTE_AS_INSTRUCTION`.

## Adversarial detection patterns

Detection uses `policy/security/adversarial_detection.v0.1.yaml`. Expanded patterns include instruction override, role impersonation, output-format override, trusted-context spoof, and system-prompt extraction. See `security_monitoring.md` for the detector and `policy/golden/prompt_injection_scenarios.v0.1.yaml` for the red-team suite.

## Golden tests

`tests/test_llm_prompt_injection_golden.py` asserts that for every scenario in `prompt_injection_scenarios.v0.1.yaml`, the agent’s action (and LLM proposal) is in `allowed_actions_for_assert` or NOOP. The blocked-delta test counts only decoder/shield blocks (not pre-LLM defense blocks) so that pre-LLM blocking does not fail the contract.
