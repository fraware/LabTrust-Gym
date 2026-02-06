"""
Episode log: determinism and JSONL structure.

Same seed + actions => identical JSONL output.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.runner import run_episode
from labtrust_gym.benchmarks.tasks import get_task
from labtrust_gym.logging.episode_log import build_log_entry, write_log_line


def test_build_log_entry_deterministic() -> None:
    """Same event + result => same JSON string (sort_keys)."""
    event = {
        "t_s": 10,
        "agent_id": "A_OPS_0",
        "action_type": "NOOP",
    }
    result = {
        "status": "ACCEPTED",
        "emits": [],
        "violations": [],
        "blocked_reason_code": None,
        "token_consumed": [],
        "hashchain": {"head_hash": "abc", "length": 1, "last_event_hash": "def"},
    }
    entry = build_log_entry(event, result)
    line1 = json.dumps(entry, sort_keys=True)
    entry2 = build_log_entry(event, result)
    line2 = json.dumps(entry2, sort_keys=True)
    assert line1 == line2
    assert entry["t_s"] == 10
    assert entry["agent_id"] == "A_OPS_0"
    assert entry["action_type"] == "NOOP"
    assert entry["status"] == "ACCEPTED"
    assert entry["hashchain_head"] == "abc"


def test_build_log_entry_includes_llm_decision() -> None:
    """When result has llm_decision, build_log_entry includes it in the entry."""
    event = {
        "t_s": 20,
        "agent_id": "ops_0",
        "action_type": "NOOP",
    }
    result = {
        "status": "ACCEPTED",
        "emits": ["LLM_DECISION"],
        "violations": [],
        "blocked_reason_code": None,
        "token_consumed": [],
        "hashchain": {"head_hash": "h1", "length": 1, "last_event_hash": "e1"},
        "llm_decision": {
            "event_id": "pz_ops_0_1",
            "backend_id": "deterministic_constrained",
            "model_id": "n/a",
            "prompt_sha256": "a" * 64,
            "response_sha256": "b" * 64,
            "latency_ms": None,
            "action_proposal": {"action_type": "NOOP", "args": {}},
            "error_code": None,
        },
    }
    entry = build_log_entry(event, result)
    assert "llm_decision" in entry
    assert entry["llm_decision"]["backend_id"] == "deterministic_constrained"
    assert entry["llm_decision"]["prompt_sha256"] == "a" * 64
    assert entry["llm_decision"]["action_proposal"]["action_type"] == "NOOP"


def test_episode_log_jsonl_determinism() -> None:
    """Same episode (seed + task) run twice => identical JSONL files."""
    task = get_task("TaskA")
    seed = 99
    with tempfile.TemporaryDirectory() as tmp:
        log1 = Path(tmp) / "ep1.jsonl"
        log2 = Path(tmp) / "ep2.jsonl"
        from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
        from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
        from labtrust_gym.envs.pz_parallel import (
            DEFAULT_DEVICE_IDS,
            DEFAULT_ZONE_IDS,
            LabTrustParallelEnv,
        )

        def env_factory(
            initial_state,
            reward_config,
            log_path=None,
        ):
            return LabTrustParallelEnv(
                num_runners=2,
                dt_s=10,
                reward_config=reward_config,
                log_path=log_path,
            )

        scripted = {
            "ops_0": ScriptedOpsAgent(),
            "runner_0": ScriptedRunnerAgent(
                zone_ids=DEFAULT_ZONE_IDS,
                device_ids=DEFAULT_DEVICE_IDS,
            ),
            "runner_1": ScriptedRunnerAgent(
                zone_ids=DEFAULT_ZONE_IDS,
                device_ids=DEFAULT_DEVICE_IDS,
            ),
        }

        log1.write_text("", encoding="utf-8")
        log2.write_text("", encoding="utf-8")
        run_episode(task, seed, env_factory, scripted, log_path=log1)
        run_episode(task, seed, env_factory, scripted, log_path=log2)

        lines1 = log1.read_text(encoding="utf-8").strip().split("\n")
        lines2 = log2.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines1) == len(lines2), (len(lines1), len(lines2))
        for i, (a, b) in enumerate(zip(lines1, lines2)):
            assert a == b, f"Line {i} differs: {a[:80]} vs {b[:80]}"
        assert log1.read_text() == log2.read_text()


def test_write_log_line_deterministic() -> None:
    """write_log_line produces identical bytes for same entry."""
    entry = {
        "t_s": 0,
        "agent_id": "A_0",
        "action_type": "TICK",
        "status": "ACCEPTED",
        "blocked_reason_code": None,
        "emits": [],
        "violations": [],
        "token_consumed": [],
        "hashchain_head": "h0",
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        delete=False,
        encoding="utf-8",
    ) as f:
        path = Path(f.name)
    try:
        with open(path, "a", encoding="utf-8") as f:
            write_log_line(f, entry)
        with open(path, "a", encoding="utf-8") as f:
            write_log_line(f, entry)
        content = path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert lines[0] == lines[1]
    finally:
        path.unlink(missing_ok=True)
