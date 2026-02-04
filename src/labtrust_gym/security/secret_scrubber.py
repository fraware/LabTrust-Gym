"""
B008: Redact secrets from debug output and logs.

Never print API keys or other secrets. Use scrub_secrets() on any string
that might contain env var values or config before logging or printing.
"""

from __future__ import annotations

import os
import re
from typing import Iterable


# Env var names that are considered secret (case-insensitive substring match)
_SECRET_NAME_PATTERNS = (
    "KEY",
    "SECRET",
    "PASSWORD",
    "PWD",
    "TOKEN",
    "CREDENTIAL",
    "AUTH",
)


def _is_secret_env_name(name: str) -> bool:
    """True if env var name looks like a secret."""
    u = name.upper()
    return any(p in u for p in _SECRET_NAME_PATTERNS)


def get_secret_env_names() -> list[str]:
    """Return list of current env var names that should be redacted."""
    return [k for k in os.environ if _is_secret_env_name(k)]


def scrub_secrets(
    text: str,
    secret_names: Iterable[str] | None = None,
    placeholder: str = "<redacted>",
) -> str:
    """
    Redact secret values from text.

    Replaces values of known secret env vars (e.g. OPENAI_API_KEY=sk-...)
    with placeholder. If secret_names is None, uses get_secret_env_names().
    """
    if secret_names is None:
        secret_names = get_secret_env_names()
    result = text
    for name in secret_names:
        val = os.environ.get(name)
        if not val:
            continue
        # Avoid replacing in places that would break structure; replace the value
        # when it appears as name=value (env-style) or "name": "value" (JSON-style)
        pattern_env = re.escape(f"{name}={val}")
        result = result.replace(pattern_env, f"{name}={placeholder}")
        pattern_json = re.escape(f'"{name}": "{val}"')
        result = result.replace(pattern_json, f'"{name}": "{placeholder}"')
        pattern_json2 = re.escape(f'"{name}": "{val}"')
        result = result.replace(pattern_json2, f'"{name}": "{placeholder}"')
        # Also replace bare value if it looks like a key (starts with sk-, etc.)
        if len(val) > 8 and (val.startswith("sk-") or "api" in name.lower()):
            result = result.replace(val, placeholder)
    return result


def scrub_dict_for_log(d: dict) -> dict:
    """
    Return a copy of d with secret-like keys redacted.

    Keys whose name (case-insensitive) contains KEY, SECRET, PASSWORD, TOKEN
    are replaced with placeholder value. Nested dicts are processed recursively.
    """
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = scrub_dict_for_log(v)
        elif _is_secret_env_name(k):
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out
