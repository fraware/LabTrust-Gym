"""
Tests for run-benchmark --profile llm_live_eval.

- Profile refuses to run unless allow-network is enabled.
- When run with allow-network, metadata and results label non_deterministic.
- LLM_TRACE bundle layout (requests_redacted.jsonl, responses.jsonl, etc.) and redaction.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")


def test_llm_live_eval_profile_refuses_without_allow_network() -> None:
    """--profile llm_live_eval exits 1 and prints message when allow-network is not set."""
    import subprocess
    import sys

    from labtrust_gym.config import get_repo_root

    root = get_repo_root()
    env = {k: v for k, v in os.environ.items() if k != "LABTRUST_ALLOW_NETWORK"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "run-benchmark",
            "--profile",
            "llm_live_eval",
            "--out",
            str(Path(root) / "tmp_refuse_test"),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1
    assert "allow-network" in result.stderr or "allow_network" in result.stderr.lower()
    assert "Refusing" in result.stderr or "refus" in result.stderr.lower()


def test_results_include_non_deterministic_when_llm_live_and_allow_network(
    tmp_path: Path,
) -> None:
    """run_benchmark with pipeline_mode=llm_live and allow_network writes non_deterministic true."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.config import get_repo_root

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-dummy"}, clear=False):
        run_benchmark(
            task_name="adversarial_disruption",
            num_episodes=1,
            base_seed=42,
            out_path=tmp_path / "results.json",
            repo_root=get_repo_root(),
            llm_backend="openai_live",
            pipeline_mode="llm_live",
            allow_network=True,
        )
    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data.get("non_deterministic") is True
    assert data.get("pipeline_mode") == "llm_live"
    assert data.get("allow_network") is True


def test_llm_trace_collector_redacts_and_writes_bundle(tmp_path: Path) -> None:
    """LLMTraceCollector records and write_to_dir produces requests_redacted.jsonl, responses.jsonl, prompt_fingerprints.json, usage.json."""
    from labtrust_gym.benchmarks.llm_trace import LLMTraceCollector

    collector = LLMTraceCollector()
    collector.record(
        messages=[{"role": "user", "content": "hello"}],
        response_raw='{"action_type":"NOOP","args":{}}',
        prompt_sha256="abc123",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    trace_dir = tmp_path / "LLM_TRACE"
    collector.write_to_dir(trace_dir)

    assert (trace_dir / "requests_redacted.jsonl").exists()
    assert (trace_dir / "responses.jsonl").exists()
    assert (trace_dir / "prompt_fingerprints.json").exists()
    assert (trace_dir / "usage.json").exists()

    lines = (
        (trace_dir / "requests_redacted.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .split("\n")
    )
    assert len(lines) == 1
    req = json.loads(lines[0])
    assert "messages" in req
    assert req["messages"][0]["content"] == "hello"

    usage_data = json.loads((trace_dir / "usage.json").read_text(encoding="utf-8"))
    assert usage_data["num_calls"] == 1
    assert usage_data["total_tokens"] == 15
