"""
UI export: labtrust ui-export produces zip with index, events, receipts_index, reason_codes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from labtrust_gym.export.ui_export import (
    UI_BUNDLE_VERSION,
    _detect_run_type,
    _normalize_event,
    export_ui_bundle,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _quick_eval_fixture_dir(tmp_path: Path) -> Path:
    """Create a minimal quick_eval layout: TaskA.json + logs/TaskA.jsonl."""
    run_dir = tmp_path / "quick_eval_fixture"
    run_dir.mkdir(parents=True)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True)
    # Copy or create TaskA.json (results.v0.2 shape)
    results_src = _repo_root() / "ui_fixtures" / "results_v0.2.json"
    if results_src.exists():
        (run_dir / "TaskA.json").write_text(
            results_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        (run_dir / "TaskA.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.2",
                    "task": "TaskA",
                    "num_episodes": 1,
                    "episodes": [{"seed": 42, "metrics": {"throughput": 2}}],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    log_src = _repo_root() / "ui_fixtures" / "episode_log.jsonl"
    if log_src.exists():
        (logs_dir / "TaskA.jsonl").write_text(
            log_src.read_text(encoding="utf-8"), encoding="utf-8"
        )
    else:
        line = json.dumps(
            {
                "action_type": "CREATE_ACCESSION",
                "agent_id": "A_RECEPTION",
                "status": "ACCEPTED",
                "blocked_reason_code": None,
                "emits": ["CREATE_ACCESSION"],
                "violations": [],
                "token_consumed": [],
                "t_s": 10,
                "event_id": "ev_0",
            }
        )
        (logs_dir / "TaskA.jsonl").write_text(line + "\n", encoding="utf-8")
    return run_dir


def test_detect_run_type_quick_eval(tmp_path: Path) -> None:
    """quick_eval layout (TaskA.json + logs/) is detected."""
    run_dir = _quick_eval_fixture_dir(tmp_path)
    assert _detect_run_type(run_dir) == "quick_eval"


def test_detect_run_type_package_release(tmp_path: Path) -> None:
    """package_release layout (_repr or _baselines) is detected."""
    run_dir = tmp_path / "release"
    run_dir.mkdir()
    (run_dir / "_repr").mkdir()
    assert _detect_run_type(run_dir) == "package_release"
    run_dir2 = tmp_path / "release2"
    run_dir2.mkdir()
    (run_dir2 / "_baselines").mkdir()
    assert _detect_run_type(run_dir2) == "package_release"


def test_normalize_event() -> None:
    """Normalized event has stable fields and episode_key."""
    raw = {
        "action_type": "CREATE_ACCESSION",
        "agent_id": "A_RECEPTION",
        "status": "ACCEPTED",
        "blocked_reason_code": None,
        "emits": ["CREATE_ACCESSION"],
        "violations": [],
        "token_consumed": [],
        "t_s": 10,
        "event_id": "ev_0",
    }
    out = _normalize_event(raw, task="TaskA", episode_index=0)
    assert out["task"] == "TaskA"
    assert out["episode_index"] == 0
    assert out["episode_key"] == "TaskA_0"
    assert out["action_type"] == "CREATE_ACCESSION"
    assert out["status"] == "ACCEPTED"
    assert out["t_s"] == 10


def test_export_ui_bundle_quick_eval(tmp_path: Path) -> None:
    """Export from quick_eval run dir produces zip with index, events, receipts_index, reason_codes."""  # noqa: E501
    run_dir = _quick_eval_fixture_dir(tmp_path)
    out_zip = tmp_path / "ui_bundle.zip"
    root = _repo_root()
    export_ui_bundle(run_dir, out_zip, repo_root=root)
    assert out_zip.is_file()
    with zipfile.ZipFile(out_zip, "r") as zf:
        names = set(zf.namelist())
        assert "index.json" in names
        assert "events.json" in names
        assert "receipts_index.json" in names
        assert "reason_codes.json" in names
        index = json.loads(zf.read("index.json"))
        assert index["ui_bundle_version"] == UI_BUNDLE_VERSION
        assert index["run_type"] == "quick_eval"
        assert "TaskA" in index["tasks"]
        assert len(index["episodes"]) >= 1
        events = json.loads(zf.read("events.json"))
        assert isinstance(events, list)
        if events:
            ev = events[0]
            assert "task" in ev and "episode_key" in ev
            assert ev.get("action_type") or ev.get("t_s") is not None
        reason_codes = json.loads(zf.read("reason_codes.json"))
        assert "version" in reason_codes and "codes" in reason_codes
        receipts_index = json.loads(zf.read("receipts_index.json"))
        assert isinstance(receipts_index, list)
        # quick_eval has no receipts
        assert len(receipts_index) == 0


def test_ui_export_cli(tmp_path: Path) -> None:
    """labtrust ui-export --run <dir> --out <zip> runs and produces zip."""
    run_dir = _quick_eval_fixture_dir(tmp_path)
    out_zip = tmp_path / "out_ui.zip"
    root = _repo_root()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "ui-export",
            "--run",
            str(run_dir),
            "--out",
            str(out_zip),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert out_zip.is_file()
    with zipfile.ZipFile(out_zip, "r") as zf:
        assert "index.json" in zf.namelist()


def test_export_ui_bundle_unknown_layout(tmp_path: Path) -> None:
    """Unknown run layout raises ValueError."""  # noqa: E501
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="Unrecognized run layout"):
        export_ui_bundle(empty, tmp_path / "out.zip", repo_root=_repo_root())
