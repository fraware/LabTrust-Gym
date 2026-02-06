"""
Local live Ollama backend: config and unit tests only (no network by default).

- Unit tests: config from env (LABTRUST_LOCAL_LLM_*), capability flags, generate error path.
- Integration (real Ollama): disabled unless LABTRUST_RUN_OLLAMA_LIVE=1 and server reachable.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from labtrust_gym.baselines.llm.backends.ollama_live import (
    BACKEND_ID,
    OllamaLiveBackend,
    _get_config,
)
from labtrust_gym.baselines.llm.provider import supports_structured_outputs


def test_ollama_get_config_defaults_when_no_env() -> None:
    """With no relevant env vars, config returns default URL, model, timeout."""
    with patch.dict(os.environ, {}, clear=False):
        for k in (
            "LABTRUST_LOCAL_LLM_URL",
            "LABTRUST_LOCAL_LLM_MODEL",
            "LABTRUST_LOCAL_LLM_TIMEOUT",
        ):
            os.environ.pop(k, None)
        url, model, timeout_s = _get_config()
    assert "localhost" in url or "11434" in url
    assert model == "llama3.2"
    assert timeout_s == 60


def test_ollama_get_config_reads_env() -> None:
    """Config reads LABTRUST_LOCAL_LLM_URL, MODEL, TIMEOUT."""
    with patch.dict(
        os.environ,
        {
            "LABTRUST_LOCAL_LLM_URL": "http://127.0.0.1:11434",
            "LABTRUST_LOCAL_LLM_MODEL": "mistral",
            "LABTRUST_LOCAL_LLM_TIMEOUT": "120",
        },
        clear=False,
    ):
        url, model, timeout_s = _get_config()
    assert "127.0.0.1" in url and "11434" in url
    assert model == "mistral"
    assert timeout_s == 120


def test_ollama_get_config_invalid_timeout_fallback() -> None:
    """Invalid LABTRUST_LOCAL_LLM_TIMEOUT falls back to 60."""
    with patch.dict(os.environ, {"LABTRUST_LOCAL_LLM_TIMEOUT": "x"}, clear=False):
        _, _, timeout_s = _get_config()
    assert timeout_s == 60


def test_ollama_backend_supports_structured_outputs_false() -> None:
    """OllamaLiveBackend has supports_structured_outputs=False (agent uses robust parse + repair)."""
    with patch.dict(os.environ, {}, clear=False):
        backend = OllamaLiveBackend()
    assert supports_structured_outputs(backend) is False
    assert backend.supports_structured_outputs is False


def test_ollama_backend_generate_returns_noop_json_on_connection_error() -> None:
    """generate() returns NOOP JSON string when request fails (no network)."""
    with patch.dict(os.environ, {"LABTRUST_LOCAL_LLM_URL": "http://localhost:11434"}, clear=False):
        backend = OllamaLiveBackend()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = OSError("Connection refused")
        out = backend.generate([{"role": "user", "content": "test"}])
    data = json.loads(out)
    assert data.get("action_type") == "NOOP"
    assert backend.last_error_code is not None
    assert backend.get_aggregate_metrics()["error_count"] == 1
    assert backend.get_aggregate_metrics()["backend_id"] == BACKEND_ID


def test_ollama_backend_aggregate_metrics_shape() -> None:
    """get_aggregate_metrics returns backend_id, model_id, total_calls, error_count, error_rate, latency."""
    with patch.dict(os.environ, {}, clear=False):
        backend = OllamaLiveBackend()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = OSError("fail")
        backend.generate([{"role": "user", "content": "x"}])
    agg = backend.get_aggregate_metrics()
    assert agg["backend_id"] == "ollama_live"
    assert "model_id" in agg
    assert agg["total_calls"] == 1
    assert agg["error_count"] == 1
    assert "error_rate" in agg
    assert "mean_latency_ms" in agg


@pytest.mark.skipif(
    not os.environ.get("LABTRUST_RUN_OLLAMA_LIVE"),
    reason="Integration: set LABTRUST_RUN_OLLAMA_LIVE=1 to run",
)
def test_ollama_live_integration_generate() -> None:
    """Optional integration: real Ollama server; skipped unless LABTRUST_RUN_OLLAMA_LIVE=1."""
    backend = OllamaLiveBackend()
    out = backend.generate(
        [
            {"role": "system", "content": "Output only valid JSON."},
            {
                "role": "user",
                "content": 'Respond with exactly: {"action_type": "NOOP", "args": {}, "reason_code": null, "token_refs": [], "rationale": "ok", "confidence": 0.5, "safety_notes": ""}',
            },
        ]
    )
    assert isinstance(out, str)
    data = json.loads(out)
    assert data.get("action_type") == "NOOP"
