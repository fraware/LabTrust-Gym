# Security detection design: pattern-based vs classifier

Adversarial and prompt-injection detection in LabTrust-Gym supports two paths: **pattern-based** (default, auditable) and an **optional classifier/judge** path. This document describes when to use each and how auditability is preserved.

## Pattern-based detection (default)

- **Where:** `src/labtrust_gym/security/adversarial_detection.py` and policy `policy/security/adversarial_detection.v0.1.yaml`.
- **Behaviour:** Keyword and regex patterns are applied to untrusted text (specimen notes, scenario notes, LLM messages). Each pattern has an id, severity (0–3), and optional reason_code. No network or external service is called. Deterministic for the same input and policy.
- **Auditability:** Patterns are listed in YAML; a reviewer can see exactly which strings or regexes trigger which severity and action. All detection decisions are explainable by matched pattern ids.

## Optional classifier path

- **When:** Enable with `use_classifier: true` in `policy/security/adversarial_detection.v0.1.yaml`, or set `LABTRUST_USE_CLASSIFIER_DETECTION=1` in the environment (overrides policy).
- **Behaviour:** On the same text inputs used for patterns, the code optionally calls a **classifier/judge** (e.g. a small local model or a dedicated API). The judge is configured via `LABTRUST_CLASSIFIER_JUDGE_URL`. The client POSTs `{"text": "<concatenated text>"}` and expects JSON `{"severity": 0–3, "flags": ["id1", ...]}`. If the URL is not set or the request fails (timeout 2s), only pattern-based detection is used.
- **Merge:** When the classifier returns a result, it is **merged** with the pattern result: severity = max(pattern_severity, classifier_severity), flags = union of pattern flags and classifier flags. Suggested action and reason_code are derived from the merged severity; if the classifier raised severity and no pattern reason_code applies, reason_code is set to `ADV_CLASSIFIER_DETECTED`.

## When to use which

| Use case | Recommendation |
|----------|----------------|
| CI, reproducibility, no network | Pattern-only (default). No external dependency; same result for same policy and input. |
| Auditable evidence for paper/release | Rely on pattern-based; document pattern set and severity mapping. Classifier can be used in addition but pattern path remains the primary, auditable signal. |
| Novel or encoded attacks | Enable classifier when you have a judge endpoint or local model that can flag semantic/encoded payloads; pattern-based remains the baseline and merge keeps both signals. |

## Auditability with classifier enabled

- Pattern-based results are always computed first; pattern flags and severities are preserved in the merged result.
- Classifier contribution is visible in `matched_pattern_ids` (classifier flags are merged into this list) and in `reason_code` when the classifier raised severity (`ADV_CLASSIFIER_DETECTED`).
- For full auditability of the classifier itself, operate and log the judge (URL, request/response, version) outside this codebase; the integration here only merges the returned severity and flags.

## See also

- [Security attack suite](security_attack_suite.md) — golden scenarios and how to enable the optional classifier.
- [Prompt injection defense](prompt_injection_defense.md) — pre-LLM check and output consistency.
