"""
Unit and integration tests for LLM backends: FixtureBackend, OpenAIHostedBackend.

- FixtureBackend: stable across runs (same messages => same response).
- OpenAIHostedBackend: raises AuthError when OPENAI_API_KEY missing (no network).
- Integration: skipped unless RUN_ONLINE_TESTS=1 and OPENAI_API_KEY set.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.baselines.llm.agent import FixtureBackend, _messages_digest
from labtrust_gym.baselines.llm.exceptions import AuthError, FixtureMissingError


# Minimal messages that match the key in tests/fixtures/llm_responses/fixtures.json
FIXTURE_MESSAGES = [
    {"role": "system", "content": "You are a test."},
    {"role": "user", "content": '{"allowed_actions": ["NOOP"]}'},
]


def test_messages_digest_deterministic() -> None:
    """_messages_digest is deterministic for same messages."""
    a = _messages_digest(FIXTURE_MESSAGES)
    b = _messages_digest(FIXTURE_MESSAGES)
    assert a == b
    assert len(a) == 64
    assert all(c in "0123456789abcdef" for c in a)


def test_fixture_backend_stable_across_runs(tmp_path: Path) -> None:
    """FixtureBackend returns the same response for the same messages across multiple calls."""
    fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "llm_responses"
    backend = FixtureBackend(fixtures_dir=fixtures_dir)
    out1 = backend.generate(FIXTURE_MESSAGES)
    out2 = backend.generate(FIXTURE_MESSAGES)
    assert out1 == out2
    assert "action_type" in out1
    assert "NOOP" in out1 or "Fixture" in out1


def test_fixture_backend_missing_raises(tmp_path: Path) -> None:
    """FixtureBackend raises FixtureMissingError when fixture is missing (not NotImplementedError)."""
    empty_dir = tmp_path / "empty_llm_fixtures"
    empty_dir.mkdir(parents=True)
    (empty_dir / "fixtures.json").write_text('{"responses": {}}')
    backend = FixtureBackend(fixtures_dir=empty_dir)
    with pytest.raises(FixtureMissingError) as exc_info:
        backend.generate(FIXTURE_MESSAGES)
    assert "record" in (exc_info.value.remediation or "").lower() or "fixture" in str(exc_info.value).lower()
    assert exc_info.value.key is not None


def test_openai_hosted_backend_missing_key_no_network() -> None:
    """OpenAIHostedBackend raises AuthError when OPENAI_API_KEY is missing; no network call."""
    from labtrust_gym.baselines.llm.backends.openai_hosted import OpenAIHostedBackend

    key_before = os.environ.pop("OPENAI_API_KEY", None)
    try:
        backend = OpenAIHostedBackend()
        with pytest.raises(AuthError) as exc_info:
            backend.generate([{"role": "user", "content": "hi"}])
        assert "OPENAI_API_KEY" in str(exc_info.value)
    finally:
        if key_before is not None:
            os.environ["OPENAI_API_KEY"] = key_before


@pytest.mark.skipif(
    os.environ.get("RUN_ONLINE_TESTS") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="RUN_ONLINE_TESTS=1 and OPENAI_API_KEY required",
)
def test_openai_hosted_backend_integration() -> None:
    """Integration: real call to OpenAI (skipped unless RUN_ONLINE_TESTS=1 and OPENAI_API_KEY set)."""
    from labtrust_gym.baselines.llm.backends.openai_hosted import OpenAIHostedBackend

    backend = OpenAIHostedBackend()
    out = backend.generate(
        [{"role": "user", "content": "Return only this JSON: {\"action_type\": \"NOOP\", \"args\": {}, \"reason_code\": null, \"token_refs\": [], \"rationale\": \"test\", \"confidence\": 1.0, \"safety_notes\": \"\"}"}]
    )
    assert "action_type" in out
    assert "NOOP" in out
