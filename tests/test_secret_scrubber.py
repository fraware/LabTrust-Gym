"""
B008: Unit tests for secret scrubber.

- Secret-like env names are redacted.
- scrub_secrets replaces env-style and JSON-style values.
- scrub_dict_for_log redacts keys recursively.
- No API keys or secrets appear in output.
"""

from __future__ import annotations

import pytest

from labtrust_gym.security.secret_scrubber import (
    get_secret_env_names,
    scrub_dict_for_log,
    scrub_secrets,
)


def test_get_secret_env_names_includes_key_vars() -> None:
    """Names containing KEY, SECRET, etc. are classified as secret."""
    with pytest.MonkeyPatch().context() as m:
        m.setenv("OPENAI_API_KEY", "sk-secret")
        m.setenv("PATH", "/usr/bin")
        names = get_secret_env_names()
        assert "OPENAI_API_KEY" in names
        assert "PATH" not in names


def test_scrub_secrets_env_style() -> None:
    """Env-style KEY=value is redacted."""
    with pytest.MonkeyPatch().context() as m:
        m.setenv("OPENAI_API_KEY", "sk-proj-abc123")
        text = "OPENAI_API_KEY=sk-proj-abc123"
        result = scrub_secrets(text, secret_names=["OPENAI_API_KEY"])
        assert "sk-proj" not in result
        assert "redacted" in result


def test_scrub_secrets_json_style() -> None:
    """JSON-style \"key\": \"value\" is redacted."""
    with pytest.MonkeyPatch().context() as m:
        m.setenv("OPENAI_API_KEY", "sk-proj-xyz")
        text = '{"OPENAI_API_KEY": "sk-proj-xyz"}'
        result = scrub_secrets(text, secret_names=["OPENAI_API_KEY"])
        assert "sk-proj" not in result
        assert "redacted" in result


def test_scrub_secrets_explicit_names() -> None:
    """When secret_names is explicit and env is set, values are redacted."""
    with pytest.MonkeyPatch().context() as m:
        m.setenv("MY_KEY", "hello")
        text = "MY_KEY=hello"
        result = scrub_secrets(text, secret_names=["MY_KEY"])
        assert "hello" not in result
        assert "redacted" in result


def test_scrub_dict_for_log_redacts_nested() -> None:
    """Dict with secret-like keys is redacted recursively."""
    d = {
        "api_key": "sk-secret",
        "model": "gpt-4",
        "nested": {"OPENAI_API_KEY": "sk-xyz", "ok": 1},
    }
    out = scrub_dict_for_log(d)
    assert out["api_key"] == "<redacted>"
    assert out["model"] == "gpt-4"
    assert out["nested"]["OPENAI_API_KEY"] == "<redacted>"
    assert out["nested"]["ok"] == 1


def test_scrub_dict_for_log_preserves_non_secret() -> None:
    """Keys that are not secret-like are preserved."""
    d = {"task": "throughput_sla", "seed": 42}
    out = scrub_dict_for_log(d)
    assert out["task"] == "throughput_sla"
    assert out["seed"] == 42
