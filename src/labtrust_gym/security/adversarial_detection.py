"""
Adversarial input detector: defensive monitoring for prompt injection and related patterns.

Consumes raw text from observations (specimen notes, scenario notes), optional LLM input/output.
Produces detection flags, severity (0-3), and suggested response action.
Default: deterministic, keyword/pattern-based, bounded; no external calls.
Optional: when use_classifier is true (policy or LABTRUST_USE_CLASSIFIER_DETECTION=1), run
classifier/judge on same texts and merge with pattern result (max severity, union of flags).
Configurable via policy/security/adversarial_detection.v0.1.yaml.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml
from labtrust_gym.security.text_normalization import (
    get_normalizers_from_policy,
    normalize_text,
)

LOG = logging.getLogger(__name__)

_CLASSIFIER_TIMEOUT_S = 2

# Cache loaded policy per path so we do not re-parse YAML on every env.step().
_ADV_POLICY_CACHE: dict[str, dict[str, Any]] = {}

_DEFAULT_ADV_POLICY: dict[str, Any] = {
    "version": "0.1",
    "severity_threshold": 1,
    "max_text_length": 2000,
    "use_classifier": False,
    "normalize_before_match": False,
    "normalizers": [],
    "max_decoded_base64_len": 2000,
    "patterns": [],
    "suggested_actions": {
        "0": "NOOP",
        "1": "NOOP",
        "2": "REQUIRE_HUMAN_REVIEW",
        "3": "THROTTLE_AGENT",
    },
}


@dataclass
class DetectionResult:
    """Result of adversarial detection run."""

    flags: list[str] = field(default_factory=list)
    severity: int = 0
    suggested_action: str = "NOOP"
    reason_code: str | None = None
    matched_pattern_ids: list[str] = field(default_factory=list)


def _get_repo_root() -> Path:
    """Return repo root (policy/ parent). Prefer LABTRUST_POLICY_DIR parent or config."""
    try:
        from labtrust_gym.config import get_repo_root as _get

        return _get()
    except Exception:
        return Path(__file__).resolve().parent.parent.parent


def load_adversarial_detection_policy(
    path: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """
    Load adversarial_detection.v0.1.yaml. Returns dict with version, severity_threshold,
    patterns, suggested_actions, max_text_length. Result is cached per path so the file
    is only parsed once per process.
    """
    if path is None:
        root = repo_root or _get_repo_root()
        path = root / "policy" / "security" / "adversarial_detection.v0.1.yaml"
    path = Path(path)
    cache_key = str(path)
    if cache_key in _ADV_POLICY_CACHE:
        return _ADV_POLICY_CACHE[cache_key]
    if os.environ.get("LABTRUST_ADVERSARIAL_USE_DEFAULT", "").strip().lower() in ("1", "true", "yes"):
        _ADV_POLICY_CACHE[cache_key] = dict(_DEFAULT_ADV_POLICY)
        return _ADV_POLICY_CACHE[cache_key]
    try:
        path_exists = path.exists()
    except OSError:
        path_exists = False
    if not path_exists:
        _ADV_POLICY_CACHE[cache_key] = dict(_DEFAULT_ADV_POLICY)
        return _ADV_POLICY_CACHE[cache_key]
    try:
        data = load_yaml(path)
    except (PolicyLoadError, Exception):
        _ADV_POLICY_CACHE[cache_key] = dict(_DEFAULT_ADV_POLICY)
        return _ADV_POLICY_CACHE[cache_key]
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
    use_classifier = bool(data.get("use_classifier", False))
    if os.environ.get("LABTRUST_USE_CLASSIFIER_DETECTION", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        use_classifier = True
    normalizers_raw = data.get("normalizers")
    if isinstance(normalizers_raw, list):
        normalizers = [str(n) for n in normalizers_raw]
    else:
        normalizers = []
    result = {
        "version": data.get("version", "0.1"),
        "severity_threshold": max(0, min(3, int(data.get("severity_threshold", 1)))),
        "max_text_length": max(100, min(100000, int(data.get("max_text_length", 2000)))),
        "use_classifier": use_classifier,
        "normalize_before_match": bool(data.get("normalize_before_match", False)),
        "normalizers": normalizers,
        "max_decoded_base64_len": max(
            500,
            min(10000, int(data.get("max_decoded_base64_len", 2000))),
        ),
        "patterns": patterns,
        "suggested_actions": suggested,
    }
    _ADV_POLICY_CACHE[cache_key] = result
    return result


def _collect_texts(context: dict[str, Any], max_len: int) -> list[str]:
    """Collect and truncate all text fields from observation context."""
    texts: list[str] = []
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


def _match_pattern(pattern_spec: dict[str, Any], text: str) -> bool:
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


def _classifier_detect(texts: list[str]) -> tuple[int, list[str]] | None:
    """
    Optional classifier/judge path. When LABTRUST_CLASSIFIER_JUDGE_URL is set,
    POST concatenated text to the judge; expect JSON {severity: 0-3, flags: [str]}.
    Returns (severity, flags) or None on missing URL, timeout, or parse failure.
    """
    url = (os.environ.get("LABTRUST_CLASSIFIER_JUDGE_URL") or "").strip()
    if not url or not texts:
        return None
    combined = "\n".join(t[:5000] for t in texts if isinstance(t, str))
    if not combined.strip():
        return None
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"text": combined}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_CLASSIFIER_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body) if body else {}
        sev = max(0, min(3, int(data.get("severity", 0))))
        flags = data.get("flags")
        if not isinstance(flags, list):
            flags = []
        flags = [str(f) for f in flags if f]
        return (sev, flags)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, ValueError, OSError) as e:
        LOG.debug("Classifier judge unavailable or failed: %s", e)
        return None


def detect_adversarial(
    observation_context: dict[str, Any],
    policy: dict[str, Any] | None = None,
    repo_root: Path | None = None,
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

    normalize_before = bool(policy.get("normalize_before_match", False))
    normalizers = get_normalizers_from_policy(policy, "normalizers")
    max_b64_len = int(policy.get("max_decoded_base64_len", 2000))
    if normalize_before and normalizers:
        texts = [normalize_text(t, normalizers, max_decoded_base64_len=max_b64_len) for t in texts]

    flags: list[str] = []
    matched_ids: list[str] = []
    max_severity = 0
    reason_code: str | None = None

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

    if policy.get("use_classifier"):
        classifier_result = _classifier_detect(texts)
        if classifier_result is not None:
            c_sev, c_flags = classifier_result
            pattern_max = max_severity
            max_severity = max(max_severity, c_sev)
            flags = list(set(flags) | set(c_flags))
            matched_ids = list(set(matched_ids) | set(c_flags))
            if c_sev > 0 and (reason_code is None or c_sev >= pattern_max):
                reason_code = reason_code or "ADV_CLASSIFIER_DETECTED"
        else:
            # Judge unavailable: fail-closed when classifier_fallback_severity_when_unavailable is set (1-3).
            fallback_sev = policy.get("classifier_fallback_severity_when_unavailable")
            if isinstance(fallback_sev, int) and 1 <= fallback_sev <= 3:
                max_severity = max(max_severity, fallback_sev)
                flags = list(set(flags) | {"ADV_CLASSIFIER_UNAVAILABLE"})
                matched_ids = list(set(matched_ids) | {"ADV_CLASSIFIER_UNAVAILABLE"})
                if reason_code is None:
                    reason_code = "ADV_CLASSIFIER_UNAVAILABLE"

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
