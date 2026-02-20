"""
Live OpenAI backend: config parsing, disabled by default, optional integration.

- Unit tests: config from env, is_available when no key, NOOP when no key.
- Integration (marked @pytest.mark.live): run with LABTRUST_RUN_LLM_LIVE=1 and
  OPENAI_API_KEY set, then: pytest tests/test_openai_live.py -m live -v
  or: pytest tests/test_openai_live.py::test_openai_live_one_episode_task_a -v
  Coord live tests (central_planner, auction_bidder, debate, agentic) run
  coord_scale with the corresponding coord method and real API; same -m live gate.
  Run all: pytest tests/test_openai_live.py -m live -v
  Use --timeout=600 for live tests (default 120s may be too short for API calls).
  One-command run for all coord live tests + trials: scripts/run_llm_live_coord_checks.ps1
  (or run_llm_live_coord_checks.sh); requires OPENAI_API_KEY set.
  No network calls in default run; no .env loading.
  Attribution/cost: set LABTRUST_LLM_TRACE=1 when tracing is desired.
"""

import json
import os
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
        api_key, model, fallback_models, timeout_s, retries = _get_config()
    assert api_key == ""
    assert model == "gpt-4o-mini"
    assert fallback_models == []
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
        api_key, model, fallback_models, timeout_s, retries = _get_config()
    assert api_key == "sk-test-key"
    assert model == "gpt-4o"
    assert timeout_s == 30
    assert retries == 2


def test_get_config_invalid_timeout_fallback() -> None:
    """Invalid LABTRUST_LLM_TIMEOUT_S falls back to 20."""
    with patch.dict(os.environ, {"LABTRUST_LLM_TIMEOUT_S": "x"}, clear=False):
        _, _, _, timeout_s, _ = _get_config()
    assert timeout_s == 20


def test_openai_backend_provider_interface_and_capabilities() -> None:
    """OpenAILiveBackend implements ProviderBackend and has capability flags."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENAI_API_KEY", None)
        backend = OpenAILiveBackend()
    assert isinstance(backend, ProviderBackend)
    assert supports_structured_outputs(backend) is True
    assert supports_tool_calls(backend) is True
    assert backend.supports_structured_outputs is True
    assert backend.supports_tool_calls is True


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


def test_propose_action_use_tools_calls_tool_path() -> None:
    """When context use_tools=True, backend uses _call_api_with_tools and returns parsed action."""
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(
        pipeline_mode="llm_live",
        allow_network=True,
        llm_backend_id=BACKEND_ID,
    )
    try:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-x"}, clear=False):
            backend = OpenAILiveBackend()
        tool_response = (
            json.dumps({
                "action_type": "TICK",
                "args": {},
                "reason_code": None,
                "token_refs": [],
                "rationale": "Tool-assisted decision.",
                "confidence": 0.9,
                "safety_notes": "",
            }),
            {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        ctx = {
            "partner_id": "",
            "now_ts_s": 0,
            "timing_mode": "explicit",
            "state_summary": {},
            "allowed_actions": ["NOOP", "TICK"],
            "active_tokens": [],
            "recent_violations": [],
            "enforcement_state": {},
            "use_tools": True,
        }
        with patch.object(
            backend,
            "_call_api_with_tools",
            return_value=tool_response,
        ):
            out = backend.propose_action(ctx)
        assert out.get("action_type") == "TICK"
        assert backend.last_metrics.get("prompt_tokens") == 10
        assert backend.last_metrics.get("completion_tokens") == 20
    finally:
        set_pipeline_config(
            pipeline_mode="deterministic",
            allow_network=False,
            llm_backend_id=None,
        )


def test_propose_action_returns_noop_when_no_key() -> None:
    """propose_action returns NOOP and sets error when no API key (pipeline allows network)."""
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(
        pipeline_mode="llm_live",
        allow_network=True,
        llm_backend_id=BACKEND_ID,
    )
    try:
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
    finally:
        set_pipeline_config(
            pipeline_mode="deterministic",
            allow_network=False,
            llm_backend_id=None,
        )


def test_generate_returns_noop_json_when_no_key() -> None:
    """generate returns NOOP JSON string when no API key (pipeline allows network)."""
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(
        pipeline_mode="llm_live",
        allow_network=True,
        llm_backend_id=BACKEND_ID,
    )
    try:
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
    finally:
        set_pipeline_config(
            pipeline_mode="deterministic",
            allow_network=False,
            llm_backend_id=None,
        )


def test_llm_decision_event_shape_live_backend_no_network() -> None:
    """LLM_DECISION event shape when OpenAILiveBackend used with no key (pipeline allows network)."""
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(
        pipeline_mode="llm_live",
        allow_network=True,
        llm_backend_id=BACKEND_ID,
    )
    try:
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
        assert "error_code" in llm
        assert llm.get("error_code") is None or isinstance(llm["error_code"], str)
        assert llm.get("used_structured_outputs") is True
        assert "prompt_id" in llm and isinstance(llm["prompt_id"], str)
        assert "prompt_version" in llm and isinstance(llm["prompt_version"], str)
        assert "prompt_fingerprint" in llm and len(llm.get("prompt_fingerprint", "")) == 64
        assert "repair_attempted" in llm and isinstance(llm["repair_attempted"], bool)
        assert "repair_succeeded" in llm and isinstance(llm["repair_succeeded"], bool)
    finally:
        set_pipeline_config(
            pipeline_mode="deterministic",
            allow_network=False,
            llm_backend_id=None,
        )


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("LABTRUST_RUN_LLM_LIVE") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="Set LABTRUST_RUN_LLM_LIVE=1 and OPENAI_API_KEY for live integration",
)
def test_openai_live_one_episode_task_a() -> None:
    """Integration: one episode TaskA with live OpenAI (run with -m live and env vars set)."""
    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results_live_task_a.json"
        r = run_benchmark(
            "throughput_sla",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=root,
            use_llm_live_openai=True,
            allow_network=True,
        )
    assert r.get("task") == "throughput_sla"
    assert len(r.get("episodes", [])) == 1


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("LABTRUST_RUN_LLM_LIVE") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="Set LABTRUST_RUN_LLM_LIVE=1 and OPENAI_API_KEY for live integration",
)
def test_openai_live_coord_scale_central_planner() -> None:
    """Integration: one episode coord_scale with llm_central_planner and live OpenAI.

    When LABTRUST_LLM_TRACE=1, also asserts metadata.llm_attribution_summary and
    by_backend are present and non-empty.
    """
    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results_live_coord_scale.json"
        r = run_benchmark(
            "coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=root,
            coord_method="llm_central_planner",
            pipeline_mode="llm_live",
            llm_backend="openai_live",
            allow_network=True,
        )
    assert r.get("task") == "coord_scale"
    assert len(r.get("episodes", [])) == 1
    assert r.get("pipeline_mode") == "llm_live"
    assert r.get("llm_backend_id") is not None
    if os.environ.get("LABTRUST_LLM_TRACE") == "1":
        summary = (r.get("metadata") or {}).get("llm_attribution_summary")
        assert summary is not None, "LABTRUST_LLM_TRACE=1 should produce attribution"
        by_backend = summary.get("by_backend") or {}
        assert isinstance(by_backend, dict) and len(by_backend) > 0


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("LABTRUST_RUN_LLM_LIVE") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="Set LABTRUST_RUN_LLM_LIVE=1 and OPENAI_API_KEY for live integration",
)
def test_openai_live_coord_scale_auction_bidder() -> None:
    """Integration: one episode coord_scale with llm_auction_bidder (round_robin) and live OpenAI."""
    import tempfile

    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    root = Path(__file__).resolve().parent.parent
    scale_config = load_scale_config_by_id(root, "small_smoke")
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results_live_coord_auction.json"
        r = run_benchmark(
            "coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=root,
            coord_method="llm_auction_bidder",
            scale_config_override=scale_config,
            pipeline_mode="llm_live",
            llm_backend="openai_live",
            allow_network=True,
        )
    assert r.get("task") == "coord_scale"
    assert len(r.get("episodes", [])) == 1
    assert r.get("pipeline_mode") == "llm_live"
    assert r.get("llm_backend_id") is not None


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("LABTRUST_RUN_LLM_LIVE") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="Set LABTRUST_RUN_LLM_LIVE=1 and OPENAI_API_KEY for live integration",
)
def test_openai_live_coord_scale_debate() -> None:
    """Integration: one episode coord_scale with llm_central_planner_debate and live OpenAI."""
    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results_live_coord_debate.json"
        r = run_benchmark(
            "coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=root,
            coord_method="llm_central_planner_debate",
            pipeline_mode="llm_live",
            llm_backend="openai_live",
            allow_network=True,
        )
    assert r.get("task") == "coord_scale"
    assert len(r.get("episodes", [])) == 1
    assert r.get("pipeline_mode") == "llm_live"
    assert r.get("llm_backend_id") is not None


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("LABTRUST_RUN_LLM_LIVE") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="Set LABTRUST_RUN_LLM_LIVE=1 and OPENAI_API_KEY for live integration",
)
def test_openai_live_coord_scale_central_planner_two_episodes() -> None:
    """Integration: two episodes coord_scale with llm_central_planner and live OpenAI."""
    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results_live_coord_scale_2ep.json"
        r = run_benchmark(
            "coord_scale",
            num_episodes=2,
            base_seed=43,
            out_path=out_path,
            repo_root=root,
            coord_method="llm_central_planner",
            pipeline_mode="llm_live",
            llm_backend="openai_live",
            allow_network=True,
        )
    assert r.get("task") == "coord_scale"
    assert len(r.get("episodes", [])) == 2
    assert r.get("pipeline_mode") == "llm_live"
    assert r.get("llm_backend_id") is not None


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("LABTRUST_RUN_LLM_LIVE") != "1" or not os.environ.get("OPENAI_API_KEY"),
    reason="Set LABTRUST_RUN_LLM_LIVE=1 and OPENAI_API_KEY for live integration",
)
def test_openai_live_coord_scale_agentic() -> None:
    """Integration: one episode coord_scale with llm_central_planner_agentic and live OpenAI."""
    import tempfile

    from labtrust_gym.benchmarks.runner import run_benchmark

    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "results_live_coord_agentic.json"
        r = run_benchmark(
            "coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=root,
            coord_method="llm_central_planner_agentic",
            pipeline_mode="llm_live",
            llm_backend="openai_live",
            allow_network=True,
        )
    assert r.get("task") == "coord_scale"
    assert len(r.get("episodes", [])) == 1
    assert r.get("pipeline_mode") == "llm_live"
    assert r.get("llm_backend_id") is not None


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("LABTRUST_RUN_LLM_LIVE") != "1"
    or not os.environ.get("OPENAI_API_KEY")
    or not os.environ.get("ANTHROPIC_API_KEY"),
    reason="Need LABTRUST_RUN_LLM_LIVE=1, OPENAI_API_KEY, ANTHROPIC_API_KEY",
)
def test_openai_live_coord_scale_per_role_backends() -> None:
    """coord_scale with distinct live backends per role; asserts attribution has >=2 backend IDs."""
    import tempfile

    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    root = Path(__file__).resolve().parent.parent
    scale_config = load_scale_config_by_id(root, "small_smoke")
    prev_trace = os.environ.get("LABTRUST_LLM_TRACE")
    try:
        os.environ["LABTRUST_LLM_TRACE"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "results_live_per_role.json"
            r = run_benchmark(
                "coord_scale",
                num_episodes=1,
                base_seed=45,
                out_path=out_path,
                repo_root=root,
                coord_method="llm_auction_bidder",
                scale_config_override=scale_config,
                pipeline_mode="llm_live",
                llm_backend="openai_live",
                allow_network=True,
                coord_planner_backend="openai_live",
                coord_bidder_backend="anthropic_live",
            )
        assert r.get("task") == "coord_scale"
        assert len(r.get("episodes", [])) == 1
        assert r.get("pipeline_mode") == "llm_live"
        summary = (r.get("metadata") or {}).get("llm_attribution_summary")
        assert summary is not None, (
            "LABTRUST_LLM_TRACE=1 should produce llm_attribution_summary"
        )
        by_backend = summary.get("by_backend") or {}
        assert isinstance(by_backend, dict)
        assert len(by_backend) >= 2, (
            "Per-role run should have >=2 backends in by_backend, got "
            f"{list(by_backend.keys())}"
        )
        for backend_id, stats in by_backend.items():
            assert isinstance(stats, dict), (
                f"by_backend[{backend_id!r}] should be a dict"
            )
            has_attr = (
                "call_count" in stats
                or "latency_ms_sum" in stats
                or "cost_usd_sum" in stats
            )
            assert has_attr, (
                f"by_backend[{backend_id!r}] should have call_count, "
                "latency_ms_sum, or cost_usd_sum"
            )
    finally:
        if prev_trace is not None:
            os.environ["LABTRUST_LLM_TRACE"] = prev_trace
        elif "LABTRUST_LLM_TRACE" in os.environ:
            os.environ.pop("LABTRUST_LLM_TRACE")
