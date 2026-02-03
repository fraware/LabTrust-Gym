"""
Live OpenAI backend: config parsing, disabled by default, optional integration.

- Unit tests: config from env, is_available when no key, NOOP when no key.
- Integration: skipped unless LABTRUST_RUN_LLM_LIVE=1 and OPENAI_API_KEY.
No network calls in default run; no .env loading.
"""

import os
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from labtrust_gym.baselines.llm.backends.openai_live import (
    BACKEND_ID,
    LLM_PROVIDER_ERROR,
    OpenAILiveBackend,
    _get_config,
)
from labtrust_gym.baselines.llm.provider import (
    ProviderBackend,
    supports_structured_outputs,
    supports_tool_calls,
)


def test_get_config_defaults_when_no_env() -> None:
    """With no relevant env vars, config returns empty key and defaults."""
    with patch.dict(os.environ, {}, clear=False):
        for k in (
            "OPENAI_API_KEY",
            "LABTRUST_OPENAI_MODEL",
            "LABTRUST_LLM_TIMEOUT_S",
            "LABTRUST_LLM_RETRIES",
        ):
            os.environ.pop(k, None)
        api_key, model, timeout_s, retries = _get_config()
    assert api_key == ""
    assert model == "gpt-4o-mini"
    assert timeout_s == 20
    assert retries == 0


def test_get_config_reads_env() -> None:
    """Config reads OPENAI_API_KEY, LABTRUST_OPENAI_MODEL, timeout, retries."""
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "sk-test-key",
            "LABTRUST_OPENAI_MODEL": "gpt-4o",
            "LABTRUST_LLM_TIMEOUT_S": "30",
            "LABTRUST_LLM_RETRIES": "2",
        },
        clear=False,
    ):
        api_key, model, timeout_s, retries = _get_config()
    assert api_key == "sk-test-key"
    assert model == "gpt-4o"
    assert timeout_s == 30
    assert retries == 2


def test_get_config_invalid_timeout_fallback() -> None:
    """Invalid LABTRUST_LLM_TIMEOUT_S falls back to 20."""
    with patch.dict(os.environ, {"LABTRUST_LLM_TIMEOUT_S": "x"}, clear=False):
        _, _, timeout_s, _ = _get_config()
    assert timeout_s == 20


def test_openai_backend_provider_interface_and_capabilities() -> None:
    """OpenAILiveBackend implements ProviderBackend and has capability flags."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENAI_API_KEY", None)
        backend = OpenAILiveBackend()
    assert isinstance(backend, ProviderBackend)
    assert supports_structured_outputs(backend) is True
    assert supports_tool_calls(backend) is False
    assert backend.supports_structured_outputs is True
    assert backend.supports_tool_calls is False


def test_openai_backend_disabled_by_default() -> None:
    """OpenAILiveBackend is_available is False when OPENAI_API_KEY not set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENAI_API_KEY", None)
        backend = OpenAILiveBackend()
    assert backend.is_available is False


def test_openai_backend_available_when_key_set() -> None:
    """OpenAILiveBackend is_available True when api_key in env."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-x"}, clear=False):
        backend = OpenAILiveBackend()
    assert backend.is_available is True


def test_propose_action_returns_noop_when_no_key() -> None:
    """propose_action returns NOOP and sets error when no API key."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENAI_API_KEY", None)
        backend = OpenAILiveBackend()
    ctx = {
        "partner_id": "",
        "now_ts_s": 0,
        "timing_mode": "explicit",
        "state_summary": {},
        "allowed_actions": ["NOOP", "TICK"],
        "active_tokens": [],
        "recent_violations": [],
        "enforcement_state": {},
    }
    out = backend.propose_action(ctx)
    assert out.get("action_type") == "NOOP"
    assert out.get("args") == {}
    assert backend.last_error_code == LLM_PROVIDER_ERROR
    assert backend.last_metrics.get("backend_id") == BACKEND_ID


def test_generate_returns_noop_json_when_no_key() -> None:
    """generate returns NOOP JSON string when no API key (LLMBackend protocol)."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENAI_API_KEY", None)
        backend = OpenAILiveBackend()
    messages = [
        {"role": "system", "content": "You are a lab agent."},
        {"role": "user", "content": "{}"},
    ]
    raw = backend.generate(messages)
    parsed = json.loads(raw)
    assert parsed.get("action_type") == "NOOP"
    assert backend.last_error_code == LLM_PROVIDER_ERROR


def test_llm_decision_event_shape_live_backend_no_network() -> None:
    """LLM_DECISION event shape is correct when using OpenAILiveBackend (no key, no network)."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENAI_API_KEY", None)
        backend = OpenAILiveBackend()
    from labtrust_gym.baselines.llm.agent import LLMAgentWithShield

    rbac = {"roles": [{"role_id": "ops", "allowed_actions": ["NOOP", "TICK"]}]}
    agent = LLMAgentWithShield(
        backend=backend,
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "ops_0"},
        use_action_proposal_schema=True,
    )
    obs = {"t_s": 0}
    _, _, meta = agent.act(obs, agent_id="ops_0")
    llm = meta.get("_llm_decision")
    assert llm is not None
    assert llm.get("backend_id") == BACKEND_ID
    assert isinstance(llm.get("model_id"), str)
    assert len(llm.get("prompt_sha256", "")) == 64
    assert len(llm.get("response_sha256", "")) == 64
    assert "action_proposal" in llm and isinstance(llm["action_proposal"], dict)
    # error_code is nullable: backend error (LLM_PROVIDER_ERROR) or decoder reason
    assert "error_code" in llm
    assert llm.get("error_code") is None or isinstance(llm["error_code"], str)
    # used_structured_outputs: OpenAILiveBackend uses strict schema (best quality)
    assert llm.get("used_structured_outputs") is True


@pytest.mark.skipif(
    os.environ.get("LABTRUST_RUN_LLM_LIVE") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason="Set LABTRUST_RUN_LLM_LIVE=1 and OPENAI_API_KEY for live integration",
)
def test_openai_live_one_episode_task_a() -> None:
    """Integration: one episode TaskA with live OpenAI when explicitly enabled."""
    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results_live_task_a.json"
        r = run_benchmark(
            "TaskA",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=root,
            use_llm_live_openai=True,
        )
    assert r.get("task") == "TaskA"
    assert len(r.get("episodes", [])) == 1
