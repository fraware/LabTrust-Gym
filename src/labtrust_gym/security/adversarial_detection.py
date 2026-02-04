"""
Adversarial input detector: defensive monitoring for prompt injection and related patterns.

Consumes raw text from observations (specimen notes, scenario notes), optional LLM input/output.
Produces detection flags, severity (0-3), and suggested response action.
Deterministic, keyword/pattern-based, bounded; no external calls.
Configurable via policy/security/adversarial_detection.v0.1.yaml.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml


@dataclass
class DetectionResult:
    """Result of adversarial detection run."""

    flags: List[str] = field(default_factory=list)
    severity: int = 0
    suggested_action: str = "NOOP"
    reason_code: Optional[str] = None
    matched_pattern_ids: List[str] = field(default_factory=list)


def _get_repo_root() -> Path:
    """Return repo root (policy/ parent). Prefer LABTRUST_POLICY_DIR parent or config."""
    try:
        from labtrust_gym.config import get_repo_root as _get

        return _get()
    except Exception:
        return Path(__file__).resolve().parent.parent.parent


def load_adversarial_detection_policy(
    path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load adversarial_detection.v0.1.yaml. Returns dict with version, severity_threshold,
    patterns, suggested_actions, max_text_length.
    """
    if path is None:
        root = repo_root or _get_repo_root()
        path = root / "policy" / "security" / "adversarial_detection.v0.1.yaml"
    path = Path(path)
    if not path.exists():
        return {
            "version": "0.1",
            "severity_threshold": 1,
            "max_text_length": 2000,
            "patterns": [],
            "suggested_actions": {
                "0": "NOOP",
                "1": "NOOP",
                "2": "REQUIRE_HUMAN_REVIEW",
                "3": "THROTTLE_AGENT",
            },
        }
    try:
        data = load_yaml(path)
    except PolicyLoadError:
        return {
            "version": "0.1",
            "severity_threshold": 1,
            "max_text_length": 2000,
            "patterns": [],
            "suggested_actions": {
                "0": "NOOP",
                "1": "NOOP",
                "2": "REQUIRE_HUMAN_REVIEW",
                "3": "THROTTLE_AGENT",
            },
        }
    if not isinstance(data, dict):
        data = {}
    patterns = data.get("patterns")
    if not isinstance(patterns, list):
        patterns = []
    suggested = data.get("suggested_actions")
    if not isinstance(suggested, dict):
        suggested = {
            "0": "NOOP",
            "1": "NOOP",
            "2": "REQUIRE_HUMAN_REVIEW",
            "3": "THROTTLE_AGENT",
        }
    return {
        "version": data.get("version", "0.1"),
        "severity_threshold": max(0, min(3, int(data.get("severity_threshold", 1)))),
        "max_text_length": max(
            100, min(100000, int(data.get("max_text_length", 2000)))
        ),
        "patterns": patterns,
        "suggested_actions": suggested,
    }


def _collect_texts(context: Dict[str, Any], max_len: int) -> List[str]:
    """Collect and truncate all text fields from observation context."""
    texts: List[str] = []
    for key in ("specimen_notes", "scenario_notes", "llm_output_text"):
        raw = context.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            s = raw[:max_len] if len(raw) > max_len else raw
            if s.strip():
                texts.append(s)
        elif isinstance(raw, list):
            for item in raw:
                s = item if isinstance(item, str) else str(item)
                s = s[:max_len] if len(s) > max_len else s
                if s.strip():
                    texts.append(s)
    llm_messages = context.get("llm_messages")
    if isinstance(llm_messages, list):
        for msg in llm_messages:
            if isinstance(msg, dict):
                content = msg.get("content") or msg.get("text") or ""
            else:
                content = str(msg)
            s = content[:max_len] if len(content) > max_len else content
            if s.strip():
                texts.append(s)
    return texts


def _match_pattern(pattern_spec: Dict[str, Any], text: str) -> bool:
    """Return True if text matches pattern (substring case-insensitive or re: regex)."""
    pat = pattern_spec.get("pattern")
    if not isinstance(pat, str) or not pat:
        return False
    if pat.startswith("re:"):
        try:
            return re.search(pat[3:].strip(), text, re.IGNORECASE) is not None
        except re.error:
            return False
    return pat.lower() in text.lower()


def detect_adversarial(
    observation_context: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> DetectionResult:
    """
    Run adversarial detection on observation context.

    observation_context: dict with optional keys specimen_notes (str or list),
    scenario_notes (str), llm_messages (list of dict/str), llm_output_text (str).
    policy: from load_adversarial_detection_policy(); if None, loaded from repo.
    Returns DetectionResult with flags, severity (0-3), suggested_action, reason_code.
    """
    if policy is None:
        policy = load_adversarial_detection_policy(repo_root=repo_root)
    max_len = int(policy.get("max_text_length", 2000))
    patterns = policy.get("patterns") or []
    suggested_actions = policy.get("suggested_actions") or {}
    if not isinstance(suggested_actions, dict):
        suggested_actions = {}

    texts = _collect_texts(observation_context, max_len)
    if not texts:
        return DetectionResult(
            flags=[],
            severity=0,
            suggested_action=str(suggested_actions.get("0", "NOOP")),
            reason_code=None,
            matched_pattern_ids=[],
        )

    flags: List[str] = []
    matched_ids: List[str] = []
    max_severity = 0
    reason_code: Optional[str] = None

    for pat in patterns:
        if not isinstance(pat, dict):
            continue
        pat_id = pat.get("id") or ""
        sev = max(0, min(3, int(pat.get("severity", 0))))
        rc = pat.get("reason_code")
        for text in texts:
            if _match_pattern(pat, text):
                flags.append(pat_id)
                matched_ids.append(pat_id)
                if sev > max_severity:
                    max_severity = sev
                    reason_code = rc
                break

    suggested_action = str(
        suggested_actions.get(max_severity)
        or suggested_actions.get(str(max_severity))
        or suggested_actions.get(0)
        or "NOOP"
    )
    return DetectionResult(
        flags=flags,
        severity=max_severity,
        suggested_action=suggested_action,
        reason_code=reason_code,
        matched_pattern_ids=matched_ids,
    )
