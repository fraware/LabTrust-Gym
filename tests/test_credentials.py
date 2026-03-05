"""
Unit tests for central LLM credential resolution (resolve_credentials, require_credentials_for_backend).

Verifies: no-key backends return {}, OpenAI/Anthropic require keys and return api_key dict,
fail-fast is no-op for deterministic/ollama, and backend constructor injection works.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from labtrust_gym.baselines.llm.credentials import (
    ANTHROPIC_KEY_BACKENDS,
    OPENAI_KEY_BACKENDS,
    require_credentials_for_backend,
    resolve_credentials,
)


def test_openai_key_backends_set() -> None:
    """OPENAI_KEY_BACKENDS contains expected live backends."""
    assert OPENAI_KEY_BACKENDS == frozenset({"openai_live", "openai_responses", "openai_hosted"})


def test_anthropic_key_backends_set() -> None:
    """ANTHROPIC_KEY_BACKENDS contains anthropic_live."""
    assert ANTHROPIC_KEY_BACKENDS == frozenset({"anthropic_live"})


def test_resolve_credentials_deterministic_returns_empty() -> None:
    """Deterministic and other non-live backends return empty dict."""
    assert resolve_credentials("deterministic", None) == {}
    assert resolve_credentials("deterministic_constrained", None) == {}
    assert resolve_credentials("ollama_live", None) == {}
    assert resolve_credentials("unknown_backend", None) == {}


def test_resolve_credentials_openai_requires_key() -> None:
    """openai_live without OPENAI_API_KEY raises ValueError with reason code."""
    with patch.dict(os.environ, {}, clear=False):
        env_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(ValueError) as exc_info:
                resolve_credentials("openai_live", None)
            assert "OPENAI_API_KEY" in str(exc_info.value)
            assert "OPENAI_API_KEY_MISSING" in str(exc_info.value)
        finally:
            if env_key is not None:
                os.environ["OPENAI_API_KEY"] = env_key


def test_resolve_credentials_openai_with_key_returns_api_key() -> None:
    """openai_live with OPENAI_API_KEY set returns dict with api_key."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key-123"}, clear=False):
        result = resolve_credentials("openai_live", None)
    assert result == {"api_key": "sk-test-key-123"}


def test_resolve_credentials_anthropic_requires_key() -> None:
    """anthropic_live without ANTHROPIC_API_KEY raises ValueError."""
    with patch.dict(os.environ, {}, clear=False):
        env_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(ValueError) as exc_info:
                resolve_credentials("anthropic_live", None)
            assert "ANTHROPIC_API_KEY" in str(exc_info.value)
        finally:
            if env_key is not None:
                os.environ["ANTHROPIC_API_KEY"] = env_key


def test_resolve_credentials_anthropic_with_key_returns_api_key() -> None:
    """anthropic_live with ANTHROPIC_API_KEY set returns dict with api_key."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
        result = resolve_credentials("anthropic_live", None)
    assert result == {"api_key": "sk-ant-test"}


def test_require_credentials_for_backend_no_op_for_deterministic() -> None:
    """require_credentials_for_backend does not raise for deterministic."""
    require_credentials_for_backend("deterministic", None)
    require_credentials_for_backend("ollama_live", None)


def test_require_credentials_for_backend_raises_for_openai_without_key() -> None:
    """require_credentials_for_backend raises for openai_live when key missing."""
    with patch.dict(os.environ, {}, clear=False):
        env_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            with pytest.raises(ValueError) as exc_info:
                require_credentials_for_backend("openai_live", None)
            assert "OPENAI_API_KEY" in str(exc_info.value)
        finally:
            if env_key is not None:
                os.environ["OPENAI_API_KEY"] = env_key


def test_resolve_credentials_strips_whitespace() -> None:
    """API key with leading/trailing whitespace is stripped."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "  sk-trimmed  "}, clear=False):
        result = resolve_credentials("openai_live", None)
    assert result == {"api_key": "sk-trimmed"}


def test_resolve_credentials_repo_root_none_no_error() -> None:
    """Passing repo_root=None does not error; .env is not loaded."""
    assert resolve_credentials("deterministic", None) == {}
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-ok"}, clear=False):
        assert resolve_credentials("openai_live", None) == {"api_key": "sk-ok"}


def test_resolve_credentials_openai_responses_and_hosted_same_as_live() -> None:
    """openai_responses and openai_hosted use same key resolution as openai_live."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-unified"}, clear=False):
        assert resolve_credentials("openai_responses", None) == {"api_key": "sk-unified"}
        assert resolve_credentials("openai_hosted", None) == {"api_key": "sk-unified"}
