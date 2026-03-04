"""
State-of-the-art prompt-injection defenses for LLM agents in hospital lab flows.

Layers:
- Pre-LLM: run adversarial detection on untrusted text; block when severity >= threshold.
- Optional sanitization: truncate or redact untrusted content before prompt build.
- Output consistency: flag when LLM output contains long verbatim from untrusted notes.

Config: policy/security/prompt_injection_defense.v0.1.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from labtrust_gym.security.adversarial_detection import (
    detect_adversarial,
    load_adversarial_detection_policy,
)
from labtrust_gym.security.text_normalization import (
    normalize_text,
)

_DEFENSE_POLICY_CACHE: dict[str, dict[str, Any]] = {}

_DEFAULT_DEFENSE: dict[str, Any] = {
    "version": "0.1",
    "block_severity_threshold": 2,
    "block_reason_code": "PROMPT_INJECTION_DETECTED",
    "sanitizer_mode": "none",
    "max_untrusted_chars": 200,
    "sanitize_redaction_severity": 1,
    "output_consistency_check": True,
    "min_verbatim_len": 20,
    "output_consistency_normalize": False,
    "output_consistency_normalizers": [],
    "check_split_verbatim": False,
}


def _get_repo_root() -> Path:
    try:
        from labtrust_gym.config import get_repo_root as _get

        return _get()
    except Exception:
        return Path(__file__).resolve().parent.parent


def load_prompt_injection_defense_policy(
    path: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Load prompt_injection_defense.v0.1.yaml. Cached per path.
    Returns dict with block_severity_threshold, sanitizer_mode, output_consistency_check.
    When path is None and LABTRUST_PROMPT_INJECTION_DEFENSE_PRESET=paranoid, loads
    prompt_injection_defense_paranoid.v0.1.yaml (block_severity_threshold: 1).
    """
    if path is None:
        root = repo_root or _get_repo_root()
        preset = (os.environ.get("LABTRUST_PROMPT_INJECTION_DEFENSE_PRESET") or "").strip().lower()
        if preset == "paranoid":
            path = root / "policy" / "security" / "prompt_injection_defense_paranoid.v0.1.yaml"
        else:
            path = root / "policy" / "security" / "prompt_injection_defense.v0.1.yaml"
    path = Path(path)
    cache_key = str(path)
    if cache_key in _DEFENSE_POLICY_CACHE:
        return _DEFENSE_POLICY_CACHE[cache_key]
    try:
        from labtrust_gym.policy.loader import load_yaml

        if not path.exists():
            _DEFENSE_POLICY_CACHE[cache_key] = dict(_DEFAULT_DEFENSE)
            return _DEFENSE_POLICY_CACHE[cache_key]
        data = load_yaml(path)
    except Exception:
        _DEFENSE_POLICY_CACHE[cache_key] = dict(_DEFAULT_DEFENSE)
        return _DEFENSE_POLICY_CACHE[cache_key]
    if not isinstance(data, dict):
        data = {}
    result = {
        "version": data.get("version", "0.1"),
        "block_severity_threshold": max(0, min(3, int(data.get("block_severity_threshold", 2)))),
        "block_reason_code": str(data.get("block_reason_code", "PROMPT_INJECTION_DETECTED")),
        "sanitizer_mode": str(data.get("sanitizer_mode", "none")).strip().lower() or "none",
        "max_untrusted_chars": max(50, min(2000, int(data.get("max_untrusted_chars", 200)))),
        "sanitize_redaction_severity": max(0, min(3, int(data.get("sanitize_redaction_severity", 1)))),
        "output_consistency_check": bool(data.get("output_consistency_check", True)),
        "min_verbatim_len": max(10, min(500, int(data.get("min_verbatim_len", 20)))),
        "output_consistency_normalize": bool(data.get("output_consistency_normalize", False)),
        "output_consistency_normalizers": (
            [str(n) for n in data.get("output_consistency_normalizers") or []]
            if isinstance(data.get("output_consistency_normalizers"), list)
            else []
        ),
        "check_split_verbatim": bool(data.get("check_split_verbatim", False)),
    }
    _DEFENSE_POLICY_CACHE[cache_key] = result
    return result


@dataclass
class PreLLMResult:
    """Result of pre-LLM prompt-injection check."""

    block: bool = False
    reason_code: str | None = None
    severity: int = 0
    sanitized_untrusted_samples: list[dict[str, str]] = field(default_factory=list)


def _collect_untrusted_texts(state_summary: dict[str, Any]) -> list[str]:
    """Collect raw untrusted text from state_summary.untrusted_notes.samples."""
    samples = (state_summary.get("untrusted_notes") or {}).get("samples") or []
    out: list[str] = []
    for s in samples:
        if isinstance(s, dict) and isinstance(s.get("text"), str):
            out.append(s["text"])
    return out


def pre_llm_prompt_injection_check(
    state_summary: dict[str, Any],
    defense_policy: dict[str, Any] | None = None,
    adversarial_policy: dict[str, Any] | None = None,
    repo_root: Path | None = None,
) -> PreLLMResult:
    """
    Run adversarial detection on untrusted text from state_summary.
    If severity >= block_severity_threshold, return block=True and reason_code.
    Optionally apply sanitizer: when sanitizer_mode is redact and severity >=
    sanitize_redaction_severity, return sanitized_untrusted_samples with text replaced.
    """
    policy = defense_policy or load_prompt_injection_defense_policy(repo_root=repo_root)
    adv_policy = adversarial_policy or load_adversarial_detection_policy(repo_root=repo_root)
    texts = _collect_untrusted_texts(state_summary)
    if not texts:
        return PreLLMResult(
            block=False,
            sanitized_untrusted_samples=(list((state_summary.get("untrusted_notes") or {}).get("samples") or [])),
        )

    obs_ctx: dict[str, Any] = {
        "specimen_notes": "\n".join(texts),
        "scenario_notes": "",
    }
    det = detect_adversarial(obs_ctx, policy=adv_policy)
    block_threshold = int(policy.get("block_severity_threshold", 2))
    block = det.severity >= block_threshold and bool(det.flags)
    reason_code = str(policy.get("block_reason_code", "PROMPT_INJECTION_DETECTED"))
    sanitized: list[dict[str, str]] = []
    samples = list((state_summary.get("untrusted_notes") or {}).get("samples") or [])
    sanitizer_mode = str(policy.get("sanitizer_mode", "none")).strip().lower()
    redaction_sev = int(policy.get("sanitize_redaction_severity", 1))
    max_chars = int(policy.get("max_untrusted_chars", 200))

    if sanitizer_mode == "redact" and det.severity >= redaction_sev and det.flags:
        for s in samples:
            if isinstance(s, dict):
                sanitized.append(
                    {
                        "source": str(s.get("source", "note")),
                        "text": "[UNTRUSTED_INPUT_REDACTED]",
                    }
                )
            else:
                sanitized.append({"source": "note", "text": "[UNTRUSTED_INPUT_REDACTED]"})
    elif sanitizer_mode == "truncate":
        for s in samples:
            if isinstance(s, dict):
                t = str(s.get("text", ""))[:max_chars]
                if len(str(s.get("text", ""))) > max_chars:
                    t = t + "..."
                sanitized.append(
                    {
                        "source": str(s.get("source", "note")),
                        "text": t,
                    }
                )
            else:
                sanitized.append({"source": "note", "text": ""})
    else:
        sanitized = [
            {
                "source": str(s.get("source", "note")),
                "text": str(s.get("text", ""))[:max_chars],
            }
            for s in samples
            if isinstance(s, dict)
        ]
        if not sanitized:
            sanitized = list(samples) if isinstance(samples, list) else []

    return PreLLMResult(
        block=block,
        reason_code=reason_code if block else None,
        severity=det.severity,
        sanitized_untrusted_samples=sanitized,
    )


def _normalize_for_consistency(
    text: str,
    normalizers: list[str],
    max_decoded_base64_len: int = 2000,
) -> str:
    """Apply allowlisted normalizers for output-consistency comparison (no base64 append)."""
    if not text or not normalizers:
        return text.strip()
    # Use same normalizers but omit decode_base64_scan for output/sample text (we compare surface form).
    allowed = [n for n in normalizers if n in ("strip_format_chars", "nfkc", "collapse_whitespace")]
    if not allowed:
        return text.strip()
    return normalize_text(text, allowed, max_decoded_base64_len=max_decoded_base64_len).strip()


def _split_verbatim_flagged(
    normalized_output: str,
    normalized_sample: str,
    min_verbatim_len: int,
    min_segment_len: int = 2,
) -> bool:
    """
    True if some split of normalized_sample (two contiguous segments) appears in
    normalized_output with total length >= min_verbatim_len (PI-EVASION-SPLIT style).
    """
    if len(normalized_sample) < min_verbatim_len or len(normalized_output) < min_verbatim_len:
        return False
    # Split at every position such that both segments have at least min_segment_len chars.
    for i in range(min_segment_len, len(normalized_sample) - min_segment_len + 1):
        seg1 = normalized_sample[:i]
        seg2 = normalized_sample[i:]
        if len(seg1) + len(seg2) < min_verbatim_len:
            continue
        concatenated = seg1 + seg2
        with_space = seg1 + " " + seg2
        if concatenated in normalized_output or with_space in normalized_output:
            return True
    return False


def output_consistency_check(
    llm_output_text: str,
    untrusted_samples: list[dict[str, str]],
    min_verbatim_len: int = 20,
    normalizers: list[str] | None = None,
    check_split_verbatim: bool = False,
    max_decoded_base64_len: int = 2000,
) -> tuple[bool, str | None]:
    """
    Return (is_flagged, reason_code).
    Flag when llm_output_text contains verbatim substring (len >= min_verbatim_len)
    from any untrusted sample (instruction leakage / echo). When normalizers are
    provided, both output and sample text are normalized before comparison (same
    allowlist as detector: strip_format_chars, nfkc, collapse_whitespace). When
    check_split_verbatim is True, also flag if two contiguous segments of a sample
    appear adjacently in normalized output (PI-EVASION-SPLIT style).
    """
    if not untrusted_samples or not llm_output_text or min_verbatim_len < 1:
        return False, None
    norm_list = list(normalizers) if normalizers else []
    if norm_list:
        text = _normalize_for_consistency(llm_output_text, norm_list, max_decoded_base64_len)
    else:
        text = llm_output_text.strip()
    if len(text) < min_verbatim_len:
        return False, None
    for s in untrusted_samples:
        raw = s.get("text") if isinstance(s, dict) else str(s)
        if not isinstance(raw, str):
            continue
        if norm_list:
            raw_norm = _normalize_for_consistency(raw, norm_list, max_decoded_base64_len)
        else:
            raw_norm = raw.strip()
        if len(raw_norm) < min_verbatim_len:
            continue
        if raw_norm in text:
            return True, "UNTRUSTED_NOTE_AS_INSTRUCTION"
        for i in range(0, len(raw_norm) - min_verbatim_len + 1):
            chunk = raw_norm[i : i + min_verbatim_len]
            if chunk in text:
                return True, "UNTRUSTED_NOTE_AS_INSTRUCTION"
        if check_split_verbatim and len(raw_norm) >= min_verbatim_len:
            if _split_verbatim_flagged(text, raw_norm, min_verbatim_len):
                return True, "UNTRUSTED_NOTE_AS_INSTRUCTION"
    return False, None
