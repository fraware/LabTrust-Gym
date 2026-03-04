"""
Episode bundle builder: build_bundle, loaders, build_bundle_from_run_dir.

Tests use minimal inline fixtures or temp dirs. Lab design uses explicit
lab_design dict to avoid pettingzoo in most tests; build_bundle_from_run_dir
requires pettingzoo for export_lab_design_json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from labtrust_gym.export.episode_bundle import (
    BUNDLE_VERSION,
    build_bundle,
    build_bundle_from_run_dir,
    load_coord_decisions,
    load_episode_log,
    load_method_trace,
    write_bundle,
)

# Minimal lab_design for tests that do not need the real env (avoids pettingzoo).
MINIMAL_LAB_DESIGN = {
    "zones": [f"Z_{i}" for i in range(10)],
    "zone_labels": {f"Z_{i}": f"Zone{i}" for i in range(10)},
    "devices": ["D1", "D2", "D3", "D4", "D5", "D6"],
    "specimen_status_order": [
        "arrived_at_reception",
        "accessioning",
        "accepted",
        "held",
        "rejected",
        "in_transit",
        "separated",
        "unknown",
    ],
    "device_zone": {},
}


def _minimal_entry(t_s: int, agent_id: str, action_type: str = "NOOP") -> dict:
    return {
        "t_s": t_s,
        "agent_id": agent_id,
        "action_type": action_type,
        "status": "ACCEPTED",
        "blocked_reason_code": None,
        "emits": [action_type],
        "violations": [],
        "token_consumed": [],
        "hashchain_head": None,
    }


def test_build_bundle_groups_by_ts() -> None:
    """Bundle groups episode entries by t_s; stepIndex is 0-based; agents sorted."""
    entries = [
        _minimal_entry(0, "A_OPS_0"),
        _minimal_entry(0, "A_RUNNER_0"),
        _minimal_entry(10, "A_OPS_0"),
        _minimal_entry(10, "A_RUNNER_0"),
    ]
    bundle = build_bundle(entries, lab_design=MINIMAL_LAB_DESIGN)
    assert bundle["version"] == BUNDLE_VERSION
    assert len(bundle["steps"]) == 2
    assert bundle["steps"][0]["stepIndex"] == 0
    assert bundle["steps"][0]["t_s"] == 0
    assert len(bundle["steps"][0]["entries"]) == 2
    assert bundle["steps"][1]["stepIndex"] == 1
    assert bundle["steps"][1]["t_s"] == 10
    assert len(bundle["steps"][1]["entries"]) == 2
    assert bundle["agents"] == ["A_OPS_0", "A_RUNNER_0"]
    assert bundle["lab_design"]["zones"] == MINIMAL_LAB_DESIGN["zones"]
    assert len(bundle["lab_design"]["zones"]) == 10


def test_build_bundle_merges_method_trace_and_coord() -> None:
    """method_trace and coord_decisions attach by step index when provided."""
    entries = [
        _minimal_entry(0, "runner_0"),
        _minimal_entry(0, "runner_1"),
        _minimal_entry(10, "runner_0"),
        _minimal_entry(10, "runner_1"),
    ]
    method_trace = {
        0: {"method_id": "whca", "t_step": 0, "stage": "propose", "hash_or_summary": "abc"},
        1: {"method_id": "whca", "t_step": 1, "stage": "propose", "hash_or_summary": "def"},
    }
    coord_decisions = {
        0: {"method_id": "whca", "t_step": 0, "actions": [], "safety_shield_applied": True},
        1: {"method_id": "whca", "t_step": 1, "actions": [], "safety_shield_applied": True},
    }
    bundle = build_bundle(
        entries,
        method_trace_by_step=method_trace,
        coord_decisions_by_step=coord_decisions,
        lab_design=MINIMAL_LAB_DESIGN,
    )
    assert "method_trace" in bundle["steps"][0]
    assert bundle["steps"][0]["method_trace"]["method_id"] == "whca"
    assert bundle["steps"][0]["method_trace"]["hash_or_summary"] == "abc"
    assert "coord_decision" in bundle["steps"][0]
    assert bundle["steps"][0]["coord_decision"]["safety_shield_applied"]
    assert "method_trace" in bundle["steps"][1]
    assert "coord_decision" in bundle["steps"][1]


def test_load_episode_log() -> None:
    """load_episode_log parses JSONL and returns list of entries."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(json.dumps(_minimal_entry(0, "A")) + "\n")
        f.write(json.dumps(_minimal_entry(0, "B")) + "\n")
        path = Path(f.name)
    try:
        loaded = load_episode_log(path)
        assert len(loaded) == 2
        assert loaded[0]["agent_id"] == "A"
        assert loaded[1]["agent_id"] == "B"
    finally:
        path.unlink()


def test_load_method_trace() -> None:
    """load_method_trace returns map t_step -> event."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write('{"t_step": 0, "method_id": "m1", "stage": "propose"}\n')
        f.write('{"t_step": 1, "method_id": "m1", "stage": "propose"}\n')
        path = Path(f.name)
    try:
        by_step = load_method_trace(path)
        assert by_step[0]["method_id"] == "m1"
        assert by_step[1]["method_id"] == "m1"
    finally:
        path.unlink()


def test_load_coord_decisions() -> None:
    """load_coord_decisions returns map step index -> record."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write('{"t_step": 0, "method_id": "c1", "actions": []}\n')
        path = Path(f.name)
    try:
        by_step = load_coord_decisions(path)
        assert by_step[0]["method_id"] == "c1"
    finally:
        path.unlink()


def test_write_bundle(tmp_path: Path) -> None:
    """write_bundle writes JSON and creates parent dirs."""
    entries = [_minimal_entry(0, "A")]
    bundle = build_bundle(entries, lab_design=MINIMAL_LAB_DESIGN)
    out = tmp_path / "sub" / "episode_bundle.json"
    write_bundle(bundle, out)
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["version"] == BUNDLE_VERSION
    assert len(loaded["steps"]) == 1


def test_build_bundle_from_run_dir_fails_without_log() -> None:
    """build_bundle_from_run_dir raises when no episode log."""
    with tempfile.TemporaryDirectory() as d:
        run_dir = Path(d)
        with pytest.raises(FileNotFoundError, match="No episode log found"):
            build_bundle_from_run_dir(run_dir)


def test_build_bundle_from_run_dir_succeeds_with_fixture(tmp_path: Path) -> None:
    """With episode_log.jsonl in run dir, build_bundle_from_run_dir works."""
    pytest.importorskip("pettingzoo")
    log_path = tmp_path / "episode_log.jsonl"
    lines = [
        json.dumps(_minimal_entry(0, "A_OPS_0")),
        json.dumps(_minimal_entry(0, "A_RUNNER_0")),
        json.dumps(_minimal_entry(10, "A_OPS_0")),
        json.dumps(_minimal_entry(10, "A_RUNNER_0")),
    ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    bundle = build_bundle_from_run_dir(tmp_path)
    assert bundle["version"] == BUNDLE_VERSION
    assert len(bundle["steps"]) == 2
    assert len(bundle["steps"][0]["entries"]) == 2
    assert "lab_design" in bundle
    assert len(bundle["lab_design"]["zones"]) == 10
    assert "meta" in bundle
    assert "source_log" in bundle["meta"]
