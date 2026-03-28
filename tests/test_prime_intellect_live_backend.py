"""Unit tests for Prime Intellect live backend (no network)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from labtrust_gym.baselines.llm.backends.prime_intellect_live import (
    BACKEND_ID,
    PrimeIntellectLiveBackend,
    prime_inference_openai_sdk_kwargs,
)


def test_backend_id_constant() -> None:
    assert BACKEND_ID == "prime_intellect_live"


def test_prime_inference_openai_sdk_kwargs_default_base() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LABTRUST_PRIME_INTELLECT_BASE_URL", None)
        os.environ.pop("LABTRUST_PRIME_TEAM_ID", None)
        kw = prime_inference_openai_sdk_kwargs()
    assert kw["openai_base_url"] == "https://api.pinference.ai/api/v1"
    assert "openai_default_headers" not in kw


def test_prime_inference_openai_sdk_kwargs_team_header() -> None:
    with patch.dict(os.environ, {"LABTRUST_PRIME_TEAM_ID": "team-xyz"}, clear=False):
        kw = prime_inference_openai_sdk_kwargs()
    assert kw["openai_default_headers"] == {"X-Prime-Team-ID": "team-xyz"}


def test_prime_backend_uses_openai_client_with_base_url() -> None:
    pytest.importorskip("openai")
    with patch.dict(
        os.environ,
        {
            "PRIME_INTELLECT_API_KEY": "test-key",
            "LABTRUST_PRIME_INTELLECT_MODEL": "meta-llama/llama-3.1-8b-instruct",
        },
        clear=False,
    ):
        be = PrimeIntellectLiveBackend()
    assert be.get_aggregate_metrics()["backend_id"] == BACKEND_ID
    assert be.get_aggregate_metrics()["model_id"] == "meta-llama/llama-3.1-8b-instruct"

    mock_create = MagicMock()

    class _Msg:
        refusal = None
        content = '{"action_type":"NOOP","args":{},"reason_code":null,"token_refs":[],"rationale":"x","confidence":1.0,"safety_notes":"","reasoning":""}'

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3})()

    mock_create.return_value = _Resp()

    with patch.dict(
        os.environ,
        {
            "PRIME_INTELLECT_API_KEY": "test-key",
            "LABTRUST_PRIME_INTELLECT_MODEL": "meta-llama/llama-3.1-8b-instruct",
        },
        clear=False,
    ):
        be2 = PrimeIntellectLiveBackend()
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.chat.completions.create = mock_create
            raw, usage = be2._call_api(  # noqa: SLF001 — intentional white-box test
                [{"role": "user", "content": "ping"}],
                structured_output=False,
            )
    mock_oa.assert_called_once()
    _call_kw = mock_oa.call_args.kwargs
    assert _call_kw["api_key"] == "test-key"
    assert _call_kw["base_url"] == "https://api.pinference.ai/api/v1"
    assert raw.startswith("{")
    assert usage["total_tokens"] == 3


def test_prime_backend_missing_key_propose_action_noop() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PRIME_INTELLECT_API_KEY", None)
        os.environ.pop("PRIME_API_KEY", None)
        be = PrimeIntellectLiveBackend(api_key="")
    from labtrust_gym.baselines.llm.backends.openai_live import NOOP_ACTION_V01
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(pipeline_mode="llm_live", allow_network=True, llm_backend_id="prime_intellect_live")
    out = be.propose_action(
        {
            "partner_id": "ops_0",
            "policy_fingerprint": None,
            "now_ts_s": 0,
            "timing_mode": "explicit",
            "state_summary": {},
            "allowed_actions": ["NOOP"],
            "active_tokens": None,
            "recent_violations": None,
            "enforcement_state": None,
        }
    )
    assert out.get("action_type") == NOOP_ACTION_V01.get("action_type")
