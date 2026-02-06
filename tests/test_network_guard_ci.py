"""
CI tests: deterministic/offline pipelines never perform network calls.

- With OPENAI_API_KEY set (dummy), run quick-eval and reproduce with network
  blocked; assert no outbound attempt and logs explicitly state "network disabled".
- Positive: llm_live + allow_network with mocked OpenAI client asserts call is made and logged.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from tests.network_guard import (
    NETWORK_BLOCKED_MSG,
    install_network_block,
    network_guard_when_offline,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_quick_eval_no_outbound_and_logs_network_disabled(tmp_path: Path) -> None:
    """
    With OPENAI_API_KEY set and network blocked, quick-eval runs without
    outbound attempts and stderr contains "network disabled".
    """
    from labtrust_gym.cli.main import _run_quick_eval, get_repo_root

    root = get_repo_root()
    out_dir = tmp_path / "quick_eval_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    args = type("Args", (), {})()
    args.seed = 42
    args.out_dir = str(out_dir)
    args.pipeline_mode = "deterministic"
    args.allow_network = False

    stderr_buf = io.StringIO()
    restore_block = install_network_block()
    try:
        old_stderr = sys.stderr
        sys.stderr = stderr_buf
        try:
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-dummy"}, clear=False):
                rc = _run_quick_eval(args)
        finally:
            sys.stderr = old_stderr
        captured = stderr_buf.getvalue()
    finally:
        restore_block()

    assert rc == 0, f"quick-eval should succeed; stderr: {captured!r}"
    assert (
        "network disabled" in captured or "network=disabled" in captured
    ), f"Logs must state network disabled; stderr: {captured!r}"
    assert NETWORK_BLOCKED_MSG not in captured, "No outbound attempt should occur"


def test_reproduce_no_outbound_and_logs_network_disabled(tmp_path: Path) -> None:
    """
    With OPENAI_API_KEY set and network blocked, reproduce (minimal + smoke)
    runs without outbound attempts and stderr contains "network disabled".
    """
    from labtrust_gym.studies.reproduce import run_reproduce

    root = _repo_root()
    out_dir = tmp_path / "repro_out"
    stderr_buf = io.StringIO()
    restore_block = install_network_block()
    try:
        old_stderr = sys.stderr
        sys.stderr = stderr_buf
        try:
            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "sk-dummy", "LABTRUST_REPRO_SMOKE": "1"},
                clear=False,
            ):
                run_reproduce(
                    profile="minimal", out_dir=out_dir, repo_root=root, seed_base=100
                )
        finally:
            sys.stderr = old_stderr
        captured = stderr_buf.getvalue()
    finally:
        restore_block()

    assert (
        "network disabled" in captured or "network=disabled" in captured
    ), f"Logs must state network disabled; stderr: {captured!r}"
    assert NETWORK_BLOCKED_MSG not in captured, "No outbound attempt should occur"
    assert (out_dir / "taska").is_dir()
    assert (out_dir / "taskc").is_dir()


def test_llm_live_mocked_client_call_made_and_logged() -> None:
    """
    In llm_live mode with allow_network, the backend's API call path is invoked
    and the call is reflected in backend metrics (mocked _call_api to avoid real network).
    """
    from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(
        pipeline_mode="llm_live", allow_network=True, llm_backend_id="openai_live"
    )

    call_log: list[list] = []

    def fake_call_api(self: object, messages: list) -> tuple[str, dict]:
        call_log.append(messages)
        content = '{"action_type":"NOOP","args":{},"reason_code":null,"token_refs":[],"rationale":"ok","confidence":0.9,"safety_notes":""}'
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        return (content, usage)

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False):
        backend = OpenAILiveBackend()
    with patch.object(OpenAILiveBackend, "_call_api", fake_call_api):
        context = {
            "state_summary": {},
            "allowed_actions": ["NOOP", "TICK"],
            "partner_id": "",
            "policy_fingerprint": None,
            "now_ts_s": 0,
            "timing_mode": "explicit",
            "active_tokens": None,
            "recent_violations": None,
            "enforcement_state": None,
        }
        result = backend.propose_action(context)

    assert result.get("action_type") == "NOOP"
    assert len(call_log) == 1, "API call path must be invoked once"
    assert backend.last_metrics, "Backend must record metrics for the call"
    assert (
        backend.last_metrics.get("latency_ms") is not None
        or "prompt_sha256" in backend.last_metrics
    )
