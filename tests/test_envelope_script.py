"""Envelope script: run_envelope_per_method produces YAML with expected keys."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_envelope_script_produces_yaml_with_expected_keys() -> None:
    """run_envelope_per_method for one method produces envelope_<id>.yaml with method_id, step_ms_mean, etc."""
    repo = _repo_root()
    script = repo / "scripts" / "run_envelope_per_method.py"
    if not script.exists():
        pytest.skip("run_envelope_per_method.py not found")
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        import subprocess

        result = subprocess.run(
            [
                "python",
                str(repo / "scripts" / "run_envelope_per_method.py"),
                "--methods",
                "centralized_planner",
                "--steps",
                "5",
                "--out-dir",
                str(out_dir),
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        yaml_path = out_dir / "envelope_centralized_planner.yaml"
        assert yaml_path.exists()
        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert data is not None
        assert data.get("method_id") == "centralized_planner"
        assert "step_ms_mean" in data
        assert "step_ms_p95" in data
        assert isinstance(data["step_ms_mean"], (int, float))
        assert isinstance(data["step_ms_p95"], (int, float))
