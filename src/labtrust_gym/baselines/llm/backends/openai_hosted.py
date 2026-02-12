"""
OpenAI-hosted-only backend (api.openai.com, OPENAI_API_KEY).

- No base_url or gateway; uses official OpenAI SDK with api_key from env only.
- Strict timeouts and bounded retries; explicit exception types
  (AuthError, RateLimitError, ProviderUnavailable).
- Implements LLMBackend (generate -> str). Optional extra: llm_openai.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, cast

from labtrust_gym.baselines.llm.exceptions import (
    AuthError,
    LLMBackendError,
    ProviderUnavailable,
    RateLimitError,
)

LOG = logging.getLogger(__name__)

BACKEND_ID = "openai_hosted"
DEFAULT_TIMEOUT_S = 30
DEFAULT_RETRIES = 2
MAX_BACKOFF_S = 60


def _get_api_key(api_key_env: str = "OPENAI_API_KEY") -> str:
    """Return API key from environment; empty string if not set."""
    return (os.environ.get(api_key_env) or "").strip()


def _get_model() -> str:
    return (os.environ.get("LABTRUST_OPENAI_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"


def _get_timeout_and_retries() -> tuple[int, int]:
    try:
        raw = os.environ.get("LABTRUST_LLM_TIMEOUT_S", str(DEFAULT_TIMEOUT_S))
        timeout_s = int(raw)
    except ValueError:
        timeout_s = DEFAULT_TIMEOUT_S
    timeout_s = max(1, min(timeout_s, 120))
    try:
        raw_ret = os.environ.get("LABTRUST_LLM_RETRIES", str(DEFAULT_RETRIES))
        retries = int(raw_ret)
    except ValueError:
        retries = DEFAULT_RETRIES
    retries = max(0, min(retries, 5))
    return timeout_s, retries


def _map_openai_error(e: Exception) -> LLMBackendError:
    """Map OpenAI SDK / API errors to our exception types."""
    msg = str(e).lower()
    if "api_key" in msg or "authentication" in msg or "401" in msg or "invalid_api_key" in msg:
        return AuthError(str(e))
    if "429" in msg or "rate" in msg or "rate_limit" in msg:
        return RateLimitError(str(e))
    if (
        "timeout" in msg or "timed out" in msg
        or "504" in msg or "502" in msg or "503" in msg or "500" in msg
    ):
        return ProviderUnavailable(str(e))
    return ProviderUnavailable(str(e))


class OpenAIHostedBackend:
    """
    Real OpenAI-hosted backend (api.openai.com only).

    - api_key from OPENAI_API_KEY; no base_url. Raises AuthError if key
      missing (no network).
    - Strict timeouts and bounded retries; raises RateLimitError,
      ProviderUnavailable on API errors.
    """

    backend_id = BACKEND_ID

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_s: int | None = None,
        retries: int | None = None,
    ) -> None:
        self._api_key = (api_key or _get_api_key()).strip()
        self._model = (model or _get_model()).strip() or "gpt-4o-mini"
        to, ret = _get_timeout_and_retries()
        self._timeout_s = timeout_s if timeout_s is not None else to
        self._retries = retries if retries is not None else ret

    def generate(self, messages: list[dict[str, str]]) -> str:
        """
        LLMBackend protocol: call OpenAI Chat Completions, return raw text.
        Raises AuthError if OPENAI_API_KEY is missing (no network call).
        Raises RateLimitError or ProviderUnavailable on API errors after retries.
        """
        if not self._api_key:
            raise AuthError(
                "OPENAI_API_KEY is not set. Set it in the environment to use "
                "OpenAI-hosted backend."
            )
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ProviderUnavailable(
                "OpenAI SDK not installed. Install with: pip install -e '.[llm_openai]'"
            ) from e

        client = OpenAI(api_key=self._api_key)
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            if attempt > 0:
                backoff_s = min(2**attempt, MAX_BACKOFF_S)
                time.sleep(backoff_s)
            try:
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=cast(Any, messages),
                    timeout=float(self._timeout_s),
                )
            except Exception as e:
                last_exc = e
                if attempt < self._retries:
                    LOG.debug("OpenAI attempt %s failed: %s", attempt + 1, str(e)[:200])
                    continue
                raise _map_openai_error(e) from e

            choice = resp.choices[0] if resp.choices else None
            if not choice or not getattr(choice, "message", None):
                last_exc = RuntimeError("Empty response")
                if attempt < self._retries:
                    continue
                raise ProviderUnavailable(
                    "Empty response from OpenAI"
                ) from last_exc
            msg = choice.message
            content = getattr(msg, "content", None) or ""
            if not content or not content.strip():
                last_exc = RuntimeError("Empty content")
                if attempt < self._retries:
                    continue
                raise ProviderUnavailable(
                    "Empty content from OpenAI"
                ) from last_exc
            return content.strip()
        raise ProviderUnavailable(
            str(last_exc or "No response")
        ) from last_exc
