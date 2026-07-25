"""
Tests for trajectory replay: action-sequence re-execution, digests, CLI wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.orchestrator.replay import (
    canonical_episode_log_digest,
    compare_episode_logs,
    evidence_digest,
    replay_action_sequence,
    run_trajectory_replay,
)


def _minimal_actions(seed: int = 42, num_runners: int = 1, cycles: int = 4) -> dict:
    agents = ["ops_0"] + [f"runner_{i}" for i in range(num_runners)] + ["qc_0", "supervisor_0"]
    steps = []
    for c in range(cycles):
        steps.append({a: (0 if (c + i) % 2 == 0 else 1) for i, a in enumerate(agents)})
    return {"seed": seed, "num_runners": num_runners, "dt_s": 10, "steps": steps}


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("pettingzoo") is None,
    reason="pettingzoo required for action-sequence replay",
)
def test_replay_action_sequence_self_consistent(tmp_path: Path) -> None:
    """Same action sequence twice => identical digests and compare ok."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    actions = _minimal_actions()
    actions_path = tmp_path / "actions.json"
    actions_path.write_text(json.dumps(actions), encoding="utf-8")
    log_a = tmp_path / "a.jsonl"
    log_b = tmp_path / "b.jsonl"
    ea = replay_action_sequence(actions_path, log_a)
    eb = replay_action_sequence(actions_path, log_b)
    assert ea and eb
    assert canonical_episode_log_digest(ea) == canonical_episode_log_digest(eb)
    assert evidence_digest(ea) == evidence_digest(eb)
    out = compare_episode_logs(ea, eb)
    assert out["status"] == "ok"
    assert out.get("canonical_episode_log_digests_match") is True
    assert out.get("evidence_digests_match") is True


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("pettingzoo") is None,
    reason="pettingzoo required for action-sequence replay",
)
def test_run_trajectory_replay_actions(tmp_path: Path) -> None:
    """run_trajectory_replay --actions self-check writes replay_summary ok."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    actions_path = tmp_path / "actions.json"
    actions_path.write_text(json.dumps(_minimal_actions()), encoding="utf-8")
    out = tmp_path / "out"
    result = run_trajectory_replay(out_dir=out, actions_path=actions_path)
    assert result["status"] == "ok"
    summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    assert summary["status"] == "ok"
    assert summary.get("match_mode") == "exact"
    assert summary.get("canonical_episode_log_digests_match") is True


def test_run_trajectory_replay_compare_logs(tmp_path: Path) -> None:
    """Two identical logs via --episode-log/--compare-log => ok."""
    entries = [
        {
            "t_s": 0,
            "agent_id": "A1",
            "action_type": "NOOP",
            "status": "ACCEPTED",
            "blocked_reason_code": None,
            "violations": [],
            "emits": [],
            "hashchain": {"head_hash": "h0", "length": 1},
        },
        {
            "t_s": 10,
            "agent_id": "A1",
            "action_type": "TICK",
            "status": "ACCEPTED",
            "blocked_reason_code": None,
            "violations": [],
            "emits": ["DOOR_TICK"],
            "hashchain": {"head_hash": "h1", "length": 2},
        },
    ]
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    a.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries), encoding="utf-8")
    b.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries), encoding="utf-8")
    result = run_trajectory_replay(
        out_dir=tmp_path / "out",
        episode_log_path=a,
        compare_log_path=b,
    )
    assert result["status"] == "ok"


def test_compare_episode_logs_reason_code_divergence() -> None:
    """blocked_reason_code mismatch is localized."""
    ref = [
        {
            "t_s": 0,
            "agent_id": "A",
            "action_type": "QUEUE_RUN",
            "status": "BLOCKED",
            "blocked_reason_code": "RBAC_DENIED",
            "violations": [],
            "emits": [],
            "hashchain": {"head_hash": "h0"},
        }
    ]
    run = [
        {
            "t_s": 0,
            "agent_id": "A",
            "action_type": "QUEUE_RUN",
            "status": "BLOCKED",
            "blocked_reason_code": "MISSING_TOKEN",
            "violations": [],
            "emits": [],
            "hashchain": {"head_hash": "h0"},
        }
    ]
    out = compare_episode_logs(ref, run)
    assert out["status"] == "diverged"
    assert out["first_divergence_step"] == 0
    assert any(d.get("field") == "blocked_reason_code" for d in out["diffs"])


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("pettingzoo") is None,
    reason="pettingzoo required for CLI action replay",
)
def test_cli_replay_trajectory_actions(tmp_path: Path) -> None:
    """CLI handler for replay-trajectory --actions exits 0 and writes summary."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    import argparse

    from labtrust_gym.cli.main import _run_replay_trajectory

    actions_path = tmp_path / "actions.json"
    actions_path.write_text(json.dumps(_minimal_actions()), encoding="utf-8")
    out = tmp_path / "cli_out"
    args = argparse.Namespace(
        out=str(out),
        recorded_run=None,
        episode_log=None,
        compare_log=None,
        actions=str(actions_path),
        seed=None,
        num_runners=None,
        repo_root=None,
    )
    rc = _run_replay_trajectory(args)
    assert rc == 0
    summary_path = out / "replay_summary.json"
    assert summary_path.exists()
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["status"] == "ok"
