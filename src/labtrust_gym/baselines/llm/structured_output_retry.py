"""
Structured output retry and normalization (SOTA).

- When strict JSON schema response fails to parse or validate, retry once with
  free-form completion and extract_first_json_object + normalize to ActionProposal.
- _normalize_to_action_proposal(parsed) fills missing required keys with defaults.
- Opt-in via LABTRUST_LLM_RETRY_FREE_FORM=1.
"""

from __future__ import annotations

from typing import Any

from labtrust_gym.baselines.llm.parse_utils import extract_first_json_object

# Canonical NOOP shape for defaults (must match action_proposal.v0.1 required keys).
DEFAULT_ACTION_PROPOSAL: dict[str, Any] = {
    "action_type": "NOOP",
    "args": {},
    "reason_code": None,
    "token_refs": [],
    "rationale": "Parse fallback.",
    "confidence": 0.0,
    "safety_notes": "",
}


def normalize_to_action_proposal(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure parsed dict has all required ActionProposal keys; fill missing from defaults.
    Does not validate action_type against allowed list; caller must enforce.
    Coerces args to dict and token_refs to list.
    """
    out = dict(DEFAULT_ACTION_PROPOSAL)
    if not isinstance(parsed, dict):
        return out
    for key in out:
        if key not in parsed or parsed[key] is None:
            continue
        val = parsed[key]
        if key == "args":
            out["args"] = dict(val) if isinstance(val, dict) else {}
        elif key == "token_refs":
            out["token_refs"] = list(val) if isinstance(val, (list, tuple)) else []
        else:
            out[key] = val
    if "reasoning" in parsed:
        out["reasoning"] = parsed["reasoning"]
    return out


def parse_and_normalize_raw(raw: str) -> dict[str, Any]:
    """
    Extract first JSON object from raw text, parse, and normalize to ActionProposal.
    Returns DEFAULT_ACTION_PROPOSAL on any failure.
    """
    extracted = extract_first_json_object(raw)
    if extracted is None:
        return dict(DEFAULT_ACTION_PROPOSAL)
    try:
        import json

        parsed = json.loads(extracted)
    except Exception:
        return dict(DEFAULT_ACTION_PROPOSAL)
    if not isinstance(parsed, dict):
        return dict(DEFAULT_ACTION_PROPOSAL)
    return normalize_to_action_proposal(parsed)


def retry_free_form_enabled() -> bool:
    """True when LABTRUST_LLM_RETRY_FREE_FORM is 1/true/yes."""
    import os

    raw = (os.environ.get("LABTRUST_LLM_RETRY_FREE_FORM") or "").strip().lower()
    return raw in ("1", "true", "yes")
