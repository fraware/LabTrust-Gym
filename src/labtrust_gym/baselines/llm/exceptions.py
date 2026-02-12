"""
Typed exceptions for LLM backends.

- AuthError: missing or invalid API key (no network call).
- RateLimitError: provider rate limit (429).
- ProviderUnavailable: timeout, 5xx, or transient failure.
- FixtureMissingError: deterministic FixtureBackend has no fixture for the request; remediate by recording fixtures.
"""

from __future__ import annotations


class LLMBackendError(Exception):
    """Base for LLM backend errors."""


class AuthError(LLMBackendError):
    """Missing or invalid API key. No network call was made."""


class RateLimitError(LLMBackendError):
    """Provider rate limit (e.g. HTTP 429)."""


class ProviderUnavailable(LLMBackendError):
    """Timeout, 5xx, or other transient provider failure."""


class FixtureMissingError(LLMBackendError):
    """
    No fixture found for this request in deterministic mode.
    Remediation: run the record-llm-fixtures command with network enabled to record fixtures.
    """

    def __init__(
        self,
        message: str,
        *,
        key: str | None = None,
        remediation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.key = key
        self.remediation = remediation or (
            "Run the record-llm-fixtures command with network enabled to record fixtures."
        )
