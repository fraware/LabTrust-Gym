"""
Prime Intellect Inference backend (OpenAI-compatible client).

Uses the official integration pattern from Prime docs: OpenAI Python SDK with
base URL https://api.pinference.ai/api/v1 and Bearer API key.

Environment:
- PRIME_INTELLECT_API_KEY (preferred) or PRIME_API_KEY (docs alias)
- LABTRUST_PRIME_INTELLECT_MODEL (default: meta-llama/llama-3.1-70b-instruct)
- LABTRUST_PRIME_INTELLECT_BASE_URL (override gateway URL)
- LABTRUST_PRIME_INTELLECT_FALLBACK_MODEL (comma-separated, same semantics as OpenAI fallback)
- LABTRUST_PRIME_TEAM_ID (optional; sets X-Prime-Team-ID for team billing)
- LABTRUST_LLM_TIMEOUT_S, LABTRUST_LLM_RETRIES (shared with other live backends)

Requires optional extra: pip install -e ".[llm_prime_intellect]" (or llm_openai; same dependency).
"""

from __future__ import annotations

import os
from typing import Any

from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend

BACKEND_ID = "prime_intellect_live"
DEFAULT_BASE_URL = "https://api.pinference.ai/api/v1"
DEFAULT_MODEL = "meta-llama/llama-3.1-70b-instruct"


def prime_inference_openai_sdk_kwargs() -> dict[str, Any]:
    """
    Extra keyword arguments for openai.OpenAI() when calling Prime Inference.

    Returns keys: openai_base_url, and optionally openai_default_headers (team billing).
    """
    team = (os.environ.get("LABTRUST_PRIME_TEAM_ID") or "").strip()
    headers: dict[str, str] | None = {"X-Prime-Team-ID": team} if team else None
    base = (os.environ.get("LABTRUST_PRIME_INTELLECT_BASE_URL") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    out: dict[str, Any] = {"openai_base_url": base}
    if headers:
        out["openai_default_headers"] = headers
    return out


def _get_prime_config() -> tuple[str, str, list[str], int, int]:
    """Returns (api_key, model, fallback_models, timeout_s, retries)."""
    api_key = (
        os.environ.get("PRIME_INTELLECT_API_KEY") or os.environ.get("PRIME_API_KEY") or ""
    ).strip()
    model = (os.environ.get("LABTRUST_PRIME_INTELLECT_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    fallback_raw = (os.environ.get("LABTRUST_PRIME_INTELLECT_FALLBACK_MODEL") or "").strip()
    fallback_models = [m.strip() for m in fallback_raw.split(",") if m.strip()] if fallback_raw else []
    if model in fallback_models:
        fallback_models = [m for m in fallback_models if m != model]
    try:
        timeout_s = int(os.environ.get("LABTRUST_LLM_TIMEOUT_S", "20"))
    except ValueError:
        timeout_s = 20
    if timeout_s <= 0:
        timeout_s = 20
    try:
        retries = int(os.environ.get("LABTRUST_LLM_RETRIES", "0"))
    except ValueError:
        retries = 0
    retries = max(0, retries)
    return (api_key, model, fallback_models, timeout_s, retries)


class PrimeIntellectLiveBackend(OpenAILiveBackend):
    """
    Live backend for Prime Intellect Inference; same contract as OpenAILiveBackend.

    backend_id is prime_intellect_live; aggregates and transparency use this id.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        timeout_s: int | None = None,
        retries: int | None = None,
        trace_collector: Any = None,
    ) -> None:
        pk, pm, pfall, to, ret = _get_prime_config()
        base = (os.environ.get("LABTRUST_PRIME_INTELLECT_BASE_URL") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
        team = (os.environ.get("LABTRUST_PRIME_TEAM_ID") or "").strip()
        headers: dict[str, str] | None = {"X-Prime-Team-ID": team} if team else None
        override_falls: list[str] | None = None if fallback_model is not None else pfall
        super().__init__(
            api_key=(api_key or pk).strip(),
            model=(model or pm).strip() or pm,
            fallback_model=fallback_model,
            timeout_s=timeout_s if timeout_s is not None else to,
            retries=retries if retries is not None else ret,
            trace_collector=trace_collector,
            backend_id=BACKEND_ID,
            openai_base_url=base,
            openai_default_headers=headers,
            missing_api_key_message="PRIME_INTELLECT_API_KEY or PRIME_API_KEY not set",
            override_fallback_models=override_falls,
        )
