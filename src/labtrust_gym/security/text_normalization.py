"""
Shared text normalization for adversarial detection and output-consistency checks.

Reduces evasion via zero-width/homoglyphs (strip Cf/Cc, NFKC), optional base64
decode for pattern scanning, and configurable allowlist so behaviour is auditable.
Used when policy enables normalize_before_match (detector) or
output_consistency_normalize (defense). Normalizers are allowlisted by name; only
allowed steps are applied.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from typing import Any

# Allowlist of normalizer IDs; only these may be applied when specified in policy.
ALLOWED_NORMALIZER_IDS = frozenset(
    {
        "strip_format_chars",  # Remove Unicode Cf (format) and Cc (control)
        "nfkc",  # NFKC normalization (canonical + compatibility)
        "collapse_whitespace",  # Collapse runs of whitespace to single space
        "decode_base64_scan",  # Append decoded base64 spans for pattern scan (bounded)
    }
)

# Max decoded base64 length to append (safety limit).
_DEFAULT_MAX_DECODED_B64_LEN = 2000

# Base64-like pattern: at least 4 chars, only A-Za-z0-9+/=.
_B64_PATTERN = re.compile(r"[A-Za-z0-9+/]{4,}={0,2}")


def _strip_format_and_control(text: str) -> str:
    """Remove Unicode Cf (format) and Cc (control) characters."""
    return "".join(c for c in text if unicodedata.category(c) not in ("Cf", "Cc"))


def _nfkc(text: str) -> str:
    """NFKC normalization (canonical composition + compatibility)."""
    return unicodedata.normalize("NFKC", text)


def _collapse_whitespace(text: str) -> str:
    """Collapse runs of whitespace to a single space."""
    return " ".join(text.split())


def _decode_base64_span(b64_str: str, max_len: int) -> str:
    """Decode one base64 string; return decoded UTF-8 or empty. Bounded by max_len."""
    try:
        raw = base64.b64decode(b64_str, validate=True)
        if len(raw) > max_len:
            raw = raw[:max_len]
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _append_decoded_base64(text: str, max_decoded_len: int) -> str:
    """
    Find base64-looking spans in text, decode (bounded), append for scanning.
    Decoded content is appended so pattern match runs over original + decoded.
    """
    decoded_parts: list[str] = []
    total = 0
    for m in _B64_PATTERN.finditer(text):
        if total >= max_decoded_len:
            break
        part = _decode_base64_span(m.group(0), max_decoded_len - total)
        if part:
            decoded_parts.append(part)
            total += len(part)
    if not decoded_parts:
        return text
    return text + "\n" + "\n".join(decoded_parts)


def normalize_text(
    text: str,
    normalizers: list[str],
    max_decoded_base64_len: int = _DEFAULT_MAX_DECODED_B64_LEN,
) -> str:
    """
    Apply allowlisted normalizers in a fixed order. Only IDs in ALLOWED_NORMALIZER_IDS
    are applied; others are ignored. Order: strip_format_chars -> nfkc ->
    collapse_whitespace -> decode_base64_scan (appends decoded content for scanning).
    """
    if not text or not normalizers:
        return text
    allowed = [n for n in normalizers if isinstance(n, str) and n in ALLOWED_NORMALIZER_IDS]
    if not allowed:
        return text
    out = text
    if "strip_format_chars" in allowed:
        out = _strip_format_and_control(out)
    if "nfkc" in allowed:
        out = _nfkc(out)
    if "collapse_whitespace" in allowed:
        out = _collapse_whitespace(out)
    if "decode_base64_scan" in allowed:
        out = _append_decoded_base64(out, max_decoded_base64_len)
    return out


def get_normalizers_from_policy(policy: dict[str, Any], key: str = "normalizers") -> list[str]:
    """Read normalizer allowlist from policy; return list of allowed IDs."""
    raw = policy.get(key)
    if isinstance(raw, list):
        return [str(x) for x in raw if x in ALLOWED_NORMALIZER_IDS]
    return []
