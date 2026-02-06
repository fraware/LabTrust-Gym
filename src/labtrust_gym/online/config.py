"""
Online serve configuration from environment (safe defaults).

Supports B007 auth modes: off, api_key, multi_key. Default binding is local-only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# B007 auth modes
AUTH_OFF = "off"
AUTH_API_KEY = "api_key"
AUTH_MULTI_KEY = "multi_key"

# Valid roles for multi_key registry
VALID_ROLES = frozenset({"admin", "runner", "viewer"})

# Safe defaults: restrictive to prevent scraping when misconfigured
DEFAULT_RATE_LIMIT_RPS_PER_KEY = 2.0
DEFAULT_RATE_LIMIT_RPS_PER_IP = 5.0
DEFAULT_MAX_BODY_BYTES = 256 * 1024  # 256 KiB
DEFAULT_MAX_INFLIGHT = 4
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _load_key_registry(path: Path) -> list[dict[str, Any]]:
    """Load key registry from YAML: auth_keys: [ { key: str, role: str }, ... ]. Returns [] on error."""
    if not path.exists():
        return []
    try:
        from labtrust_gym.policy.loader import load_yaml

        data = load_yaml(path)
    except Exception:
        return []
    keys = data.get("auth_keys") if isinstance(data, dict) else None
    if not isinstance(keys, list):
        return []
    out = []
    for item in keys:
        if not isinstance(item, dict):
            continue
        k = item.get("key")
        r = (item.get("role") or "").strip().lower()
        if k and isinstance(k, str) and r in VALID_ROLES:
            out.append({"key": k.strip(), "role": r})
    return out


@dataclass(frozen=True)
class OnlineConfig:
    """Immutable config for online serve mode (B004 + B007)."""

    api_key: str | None
    rate_limit_rps_per_key: float
    rate_limit_rps_per_ip: float
    max_body_bytes: int
    max_inflight: int
    host: str
    port: int
    # B007
    auth_mode: str
    key_registry: tuple[dict[str, str], ...]  # ({key, role}, ...)

    @property
    def auth_required(self) -> bool:
        """True when auth is enabled (api_key or multi_key)."""
        return self.auth_mode in (AUTH_API_KEY, AUTH_MULTI_KEY)


def _parse_float(value: str | None, default: float, min_val: float = 0.1) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        v = float(value)
        return max(min_val, v)
    except ValueError:
        return default


def _parse_int(value: str | None, default: int, min_val: int = 1) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        v = int(value)
        return max(min_val, v)
    except ValueError:
        return default


def load_online_config() -> OnlineConfig:
    """
    Load online config from environment.

    B007 auth:
    - LABTRUST_AUTH_MODE: off | api_key | multi_key (default: off, or api_key if LABTRUST_ONLINE_API_KEY set).
    - LABTRUST_AUTH_KEY: single key for api_key mode (or use LABTRUST_ONLINE_API_KEY for backward compat).
    - LABTRUST_AUTH_KEY_FILE: path to YAML key registry for multi_key (auth_keys: [{ key, role }]).

    Other: LABTRUST_ONLINE_API_KEY (legacy), LABTRUST_RATE_LIMIT_*, LABTRUST_MAX_*, LABTRUST_SERVE_*.
    """
    auth_mode_raw = (os.environ.get("LABTRUST_AUTH_MODE") or "").strip().lower()
    raw_legacy = os.environ.get("LABTRUST_ONLINE_API_KEY")
    legacy_key = raw_legacy.strip() if raw_legacy and isinstance(raw_legacy, str) else None
    if legacy_key == "":
        legacy_key = None
    raw_auth_key = os.environ.get("LABTRUST_AUTH_KEY")
    auth_key = raw_auth_key.strip() if raw_auth_key and isinstance(raw_auth_key, str) else None
    if auth_key == "":
        auth_key = None
    single_key = auth_key or legacy_key
    if auth_mode_raw not in (AUTH_OFF, AUTH_API_KEY, AUTH_MULTI_KEY):
        auth_mode_raw = AUTH_OFF
    if auth_mode_raw == AUTH_OFF and single_key:
        auth_mode_raw = AUTH_API_KEY
    if auth_mode_raw == AUTH_API_KEY:
        api_key = single_key
    else:
        api_key = None
    key_registry: list[dict[str, str]] = []
    if auth_mode_raw == AUTH_MULTI_KEY:
        path_raw = os.environ.get("LABTRUST_AUTH_KEY_FILE")
        if path_raw and path_raw.strip():
            key_registry = _load_key_registry(Path(path_raw.strip()))
        if not key_registry and single_key:
            key_registry = [{"key": single_key, "role": "admin"}]
    key_registry_t = tuple(key_registry)

    return OnlineConfig(
        api_key=api_key,
        rate_limit_rps_per_key=_parse_float(
            os.environ.get("LABTRUST_RATE_LIMIT_RPS_PER_KEY"),
            DEFAULT_RATE_LIMIT_RPS_PER_KEY,
        ),
        rate_limit_rps_per_ip=_parse_float(
            os.environ.get("LABTRUST_RATE_LIMIT_RPS_PER_IP"),
            DEFAULT_RATE_LIMIT_RPS_PER_IP,
        ),
        max_body_bytes=_parse_int(
            os.environ.get("LABTRUST_MAX_BODY_BYTES"),
            DEFAULT_MAX_BODY_BYTES,
            min_val=1024,
        ),
        max_inflight=_parse_int(
            os.environ.get("LABTRUST_MAX_INFLIGHT"),
            DEFAULT_MAX_INFLIGHT,
            min_val=1,
        ),
        host=(os.environ.get("LABTRUST_SERVE_HOST") or DEFAULT_HOST).strip() or DEFAULT_HOST,
        port=_parse_int(
            os.environ.get("LABTRUST_SERVE_PORT"),
            DEFAULT_PORT,
            min_val=1,
        )
        % 65536,
        auth_mode=auth_mode_raw,
        key_registry=key_registry_t,
    )


def resolve_role(key: str | None, config: OnlineConfig) -> str | None:
    """
    Resolve role for presented key. Returns role string or None if invalid/missing.

    - auth_mode off: returns None (no role; auth not required).
    - api_key: key must match config.api_key; returns "admin".
    - multi_key: key must be in key_registry; returns that entry's role.
    """
    if not config.auth_required:
        return None
    if not key or not key.strip():
        return None
    key = key.strip()
    if config.auth_mode == AUTH_API_KEY and config.api_key and key == config.api_key:
        return "admin"
    if config.auth_mode == AUTH_MULTI_KEY:
        for entry in config.key_registry:
            if entry.get("key") == key:
                return entry.get("role") or "viewer"
    return None
