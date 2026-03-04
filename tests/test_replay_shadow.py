"""
Tests for replay and shadow: comparison logic, replay_summary.json and
shadow_comparison.json with real comparisons; divergence detected and localized.
No stub status in outputs.
"""

import json
from pathlib import Path

from labtrust_gym.orchestrator.replay import (
    compare_episode_logs,
    run_replay,
)
from labtrust_gym.orchestrator.shadow import run_shadow


def _entry(
    t_s: int = 0,
    agent_id: str = "A1",
    action_type: str = "MOVE",
    status: str = "ok",
):
    return {
        "t_s": t_s,
        "agent_id": agent_id,
        "action_type": action_type,
        "status": status,
        "violations": [],
        "emits": [],
        "hashchain": {"head_hash": "h0", "length": 1},
    }


def test_compare_episode_logs_ok():
    """Same entries -> status ok, no diffs."""
    entries = [
        _entry(0, "A1", "MOVE", "ok"),
        _entry(10, "A1", "CENTRIFUGE_START", "ok"),
    ]
    out = compare_episode_logs(entries, entries)
    assert out["status"] == "ok"
    assert out["first_divergence_step"] is None
    assert out["steps_compared"] == 2
    assert out["diffs"] == []
    assert out.get("receipt_digests_match") is True


def test_compare_episode_logs_diverged():
    """One step different -> diverged, first_divergence_step set, diffs."""
    ref = [
        _entry(0, "A1", "MOVE", "ok"),
        _entry(10, "A1", "CENTRIFUGE_START", "ok"),
    ]
    run = [
        _entry(0, "A1", "MOVE", "ok"),
        _entry(10, "A1", "CENTRIFUGE_START", "blocked"),
    ]
    out = compare_episode_logs(ref, run)
    assert out["status"] == "diverged"
    assert out["first_divergence_step"] == 1
    assert out["steps_compared"] == 2
    assert len(out["diffs"]) >= 1
    assert any(d.get("field") == "status" and d.get("step_index") == 1 for d in out["diffs"])


def test_compare_episode_logs_step_count_diverged():
    """Different step count -> diverged, first_divergence_step set."""
    ref = [_entry(0), _entry(10)]
    run = [_entry(0)]
    out = compare_episode_logs(ref, run)
    assert out["status"] == "diverged"
    assert out["first_divergence_step"] == 1
    assert any(d.get("field") == "step_count" for d in out["diffs"])


def test_run_replay_two_logs_diverged(tmp_path):
    """Two logs with deliberate divergence -> replay_summary diverged, localized."""
    ref_log = tmp_path / "ref.jsonl"
    run_log = tmp_path / "run.jsonl"
    out = tmp_path / "replay_out"
    ref_entries = [
        _entry(0, "A1", "MOVE", "ok"),
        _entry(10, "A1", "QUEUE_RUN", "ok"),
    ]
    run_entries = [
        _entry(0, "A1", "MOVE", "ok"),
        _entry(10, "A1", "QUEUE_RUN", "blocked"),
    ]
    ref_log.write_text("\n".join(json.dumps(e, sort_keys=True) for e in ref_entries))
    run_log.write_text("\n".join(json.dumps(e, sort_keys=True) for e in run_entries))

    result = run_replay(
        episode_log_path=ref_log,
        out_dir=out,
        policy_root=tmp_path,
        re_run_episode_log_path=run_log,
    )
    assert result["status"] == "diverged"
    assert result["first_divergence_step"] == 1
    assert "stub" not in json.dumps(result).lower()

    summary_path = Path(result["summary_path"])
    assert summary_path.exists()
    data = json.loads(summary_path.read_text())
    assert data["status"] == "diverged"
    assert data["first_divergence_step"] == 1
    assert len(data["diff_summary"]) >= 1
    assert "stub" not in summary_path.read_text().lower()


def test_run_replay_two_logs_ok(tmp_path):
    """Same two logs -> status ok."""
    ref_log = tmp_path / "ref.jsonl"
    run_log = tmp_path / "run.jsonl"
    out = tmp_path / "replay_out"
    entries = [_entry(0), _entry(10)]
    ref_log.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries))
    run_log.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries))

    result = run_replay(
        episode_log_path=ref_log,
        out_dir=out,
        policy_root=tmp_path,
        re_run_episode_log_path=run_log,
    )
    assert result["status"] == "ok"
    assert result["first_divergence_step"] is None
    assert Path(result["summary_path"]).exists()
    data = json.loads(Path(result["summary_path"]).read_text())
    assert data["status"] == "ok"
    assert "stub" not in json.dumps(data).lower()


def test_run_shadow_baseline_dir_no_log_returns_failed_not_stub(tmp_path):
    """baseline_run_dir with no episode log -> status failed, no stub."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    # no episode_log.jsonl
    out = tmp_path / "shadow_out"
    result = run_shadow(
        baseline_run_dir=baseline_dir,
        shadow_method_id="centralized_planner",
        out_dir=out,
        policy_root=tmp_path,
    )
    assert "stub" not in json.dumps(result).lower()
    comp_path = Path(result["comparison_path"])
    assert comp_path.exists()
    data = json.loads(comp_path.read_text())
    assert data["status"] == "failed"
    assert "stub" not in comp_path.read_text().lower()
    assert "diffs" in data
    assert "artifact_pointers" in data


def test_run_shadow_baseline_dir_with_log_and_results_produces_comparison(
    tmp_path,
):
    """baseline_run_dir with episode_log and results.json -> comparison, no stub."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    log_path = baseline_dir / "episode_log.jsonl"
    entries = [_entry(0), _entry(10)]
    log_path.write_text("\n".join(json.dumps(e, sort_keys=True) for e in entries))
    results = {
        "task": "throughput_sla",
        "seeds": [42],
        "config": {},
    }
    (baseline_dir / "results.json").write_text(json.dumps(results, indent=2))

    out = tmp_path / "shadow_out"
    result = run_shadow(
        baseline_run_dir=baseline_dir,
        shadow_method_id="scripted_runner",
        out_dir=out,
        policy_root=Path.cwd(),
    )
    assert "stub" not in json.dumps(result).lower()
    comp_path = Path(result["comparison_path"])
    data = json.loads(comp_path.read_text())
    assert data["status"] in ("ok", "diverged", "failed")
    assert "first_divergence_step" in data
    assert "steps_compared" in data
    assert "diffs" in data
    assert "artifact_pointers" in data
    if data["status"] == "diverged":
        assert data["first_divergence_step"] is not None
        assert len(data["diffs"]) > 0
