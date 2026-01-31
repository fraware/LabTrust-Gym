"""
Smoke test for labtrust reproduce: validates that the command runs in minimal
mode with tiny episode count when LABTRUST_REPRO_SMOKE=1.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")
pytest.importorskip("matplotlib")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_reproduce_smoke_minimal_runs() -> None:
    """When LABTRUST_REPRO_SMOKE=1, reproduce --profile minimal runs and writes output."""
    if os.environ.get("LABTRUST_REPRO_SMOKE", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        pytest.skip("Set LABTRUST_REPRO_SMOKE=1 to run reproduce smoke test")

    root = _repo_root()
    env = {**os.environ, "LABTRUST_REPRO_SMOKE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "labtrust_gym.cli.main",
        "reproduce",
        "--profile",
        "minimal",
        "--out",
        None,
    ]
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "repro_out"
        cmd[-1] = str(out_dir)
        result = subprocess.run(
            cmd,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"stderr={result.stderr!r} stdout={result.stdout!r}"
        )
        assert (out_dir / "spec_TaskA.yaml").exists()
        assert (out_dir / "spec_TaskC.yaml").exists()
        assert (out_dir / "taska").is_dir()
        assert (out_dir / "taskc").is_dir()
        assert (out_dir / "taska" / "manifest.json").exists()
        assert (out_dir / "taskc" / "manifest.json").exists()
        assert (out_dir / "taska" / "results").is_dir()
        assert (out_dir / "taskc" / "results").is_dir()
        assert (out_dir / "taska" / "figures").is_dir()
        assert (out_dir / "taskc" / "figures").is_dir()
