"""
Memory validators: poison pattern detection and instruction-override detection.

Used on write (reject poisoned content) and on retrieval (filter before return).
Deterministic, policy-driven; no external calls.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MEM_POISON_DETECTED = "MEM_POISON_DETECTED"
MEM_WRITE_SCHEMA_FAIL = "MEM_WRITE_SCHEMA_FAIL"


def load_memory_policy(policy_root: Path | None = None) -> dict[str, Any]:
    """Load memory_policy from policy_root. Returns root dict or default."""
    if policy_root is None:
        return _default_memory_policy()
    path = Path(policy_root) / "policy" / "memory_policy.v0.1.yaml"
    if not path.exists():
        return _default_memory_policy()
    try:
        from labtrust_gym.policy.loader import load_yaml

        data = load_yaml(path)
    except Exception:
        return _default_memory_policy()
    root = data.get("memory_policy") if isinstance(data, dict) else data
    return root if isinstance(root, dict) else _default_memory_policy()


def _default_memory_policy() -> dict[str, Any]:
    return {
        "version": "0.1",
        "allowed_fields": ["content", "summary", "role", "timestamp", "tags", "source"],
        "max_content_length": 4096,
        "max_summary_length": 256,
        "forbidden_patterns": [],
        "instruction_override_patterns": [],
    }


def _compile_patterns(patterns: list[dict[str, Any]]) -> list[tuple[re.Pattern[str], str]]:
    """Compile regex patterns from policy. Returns [(compiled, pattern_id)]."""
    out: list[tuple[re.Pattern[str], str]] = []
    for i, p in enumerate(patterns):
        if not isinstance(p, dict):
            continue
        pat = p.get("pattern")
        if not pat:
            continue
        flags_str = (p.get("flags") or "").strip()
        flags = re.IGNORECASE if "i" in flags_str else 0
        try:
            out.append((re.compile(pat, flags), p.get("id") or f"p{i}"))
        except re.error:
            continue
    return out


def check_poison(
    text: str,
    policy: dict[str, Any] | None = None,
) -> tuple[bool, str | None, str | None]:
    """
    Check text for forbidden/poison patterns.
    Returns (is_clean, reason_code, matched_id). If not clean: MEM_POISON_DETECTED.
    """
    if policy is None:
        policy = _default_memory_policy()
    patterns = _compile_patterns(policy.get("forbidden_patterns") or [])
    for compiled, pid in patterns:
        if compiled.search(text):
            return False, MEM_POISON_DETECTED, pid
    return True, None, None


def check_instruction_override(
    text: str,
    policy: dict[str, Any] | None = None,
) -> tuple[bool, str | None, str | None]:
    """
    Check text for instruction-override patterns.
    Returns (is_clean, reason_code, matched_id). If not clean: MEM_POISON_DETECTED.
    """
    if policy is None:
        policy = _default_memory_policy()
    patterns = _compile_patterns(policy.get("instruction_override_patterns") or [])
    for compiled, pid in patterns:
        if compiled.search(text):
            return False, MEM_POISON_DETECTED, pid
    return True, None, None


def check_poison_and_instruction_override(
    text: str,
    policy: dict[str, Any] | None = None,
) -> tuple[bool, str | None, str | None]:
    """
    Check both poison and instruction-override patterns. Returns (is_clean, reason_code, matched_id).
    Forbidden patterns are checked first, then instruction-override.
    """
    ok, code, mid = check_poison(text, policy)
    if not ok:
        return False, code, mid
    return check_instruction_override(text, policy)


def validate_entry_schema(
    entry: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Validate memory entry: allowed fields only, max lengths.
    Returns (ok, reason_code). On failure: MEM_WRITE_SCHEMA_FAIL.
    """
    if policy is None:
        policy = _default_memory_policy()
    allowed = set(policy.get("allowed_fields") or [])
    if allowed and entry:
        for key in entry:
            if key not in allowed:
                return False, MEM_WRITE_SCHEMA_FAIL
    max_content = int(policy.get("max_content_length") or 4096)
    max_summary = int(policy.get("max_summary_length") or 256)
    content = entry.get("content")
    if content is not None:
        s = str(content)
        if len(s) > max_content:
            return False, MEM_WRITE_SCHEMA_FAIL
    summary = entry.get("summary")
    if summary is not None:
        s = str(summary)
        if len(s) > max_summary:
            return False, MEM_WRITE_SCHEMA_FAIL
    return True, None


def filter_poison_from_entries(
    entries: list[dict[str, Any]],
    policy: dict[str, Any] | None = None,
    content_key: str = "content",
) -> tuple[list[dict[str, Any]], int]:
    """
    Remove entries that contain poison or instruction-override patterns.
    Returns (filtered_list, removed_count). Deterministic.
    """
    if policy is None:
        policy = _default_memory_policy()
    kept: list[dict[str, Any]] = []
    removed = 0
    for e in entries:
        text = e.get(content_key)
        if text is None:
            kept.append(e)
            continue
        ok, _, _ = check_poison_and_instruction_override(str(text), policy)
        if ok:
            kept.append(e)
        else:
            removed += 1
    return kept, removed
