"""
Smoke test for trust ablations study: when LABTRUST_REPRO_SMOKE=1, run a tiny
trust_ablations study and assert artifact files exist (manifest, results, figures, summary table).
"""

from __future__ import annotations

import json
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


def test_trust_ablations_smoke_artifact_files_exist() -> None:
    """When LABTRUST_REPRO_SMOKE=1, run trust_ablations study (tiny) and assert artifact files exist."""
    if os.environ.get("LABTRUST_REPRO_SMOKE", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        pytest.skip("Set LABTRUST_REPRO_SMOKE=1 to run trust ablations smoke test")

    root = _repo_root()
    spec_path = root / "policy" / "studies" / "trust_ablations.v0.1.yaml"
    if not spec_path.exists():
        pytest.skip(f"trust_ablations spec not found: {spec_path}")

    env = {**os.environ, "LABTRUST_REPRO_SMOKE": "1"}
    with __import__("tempfile").TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "trust_ablations_out"
        cmd_run = [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "run-study",
            "--spec",
            str(spec_path),
            "--out",
            str(out_dir),
        ]
        result = subprocess.run(
            cmd_run,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, (
            f"run-study failed: stderr={result.stderr!r} stdout={result.stdout!r}"
        )

        assert (out_dir / "manifest.json").exists()
        assert (out_dir / "conditions.jsonl").exists()
        manifest = json.loads((out_dir / "manifest.json").read_text())
        condition_ids = manifest.get("condition_ids") or []
        condition_labels = manifest.get("condition_labels") or []
        assert len(condition_ids) >= 2
        assert len(condition_labels) == len(condition_ids)

        for cid in condition_ids:
            assert (out_dir / "results" / cid / "results.json").exists()
            assert (out_dir / "logs" / cid / "episodes.jsonl").exists()

        cmd_plots = [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "make-plots",
            str(out_dir),
        ]
        result_plots = subprocess.run(
            cmd_plots,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result_plots.returncode == 0, (
            f"make-plots failed: stderr={result_plots.stderr!r}"
        )

        fig_dir = out_dir / "figures"
        tables_dir = fig_dir / "data_tables"
        assert fig_dir.is_dir()
        assert tables_dir.is_dir()
        assert (tables_dir / "summary.csv").exists()
        assert (tables_dir / "paper_table.md").exists()
        assert (tables_dir / "throughput_vs_violations.csv").exists()
        assert (tables_dir / "trust_cost_vs_p95_tat.csv").exists()
        assert (fig_dir / "throughput_vs_violations.png").exists() or (
            fig_dir / "throughput_vs_violations.svg"
        ).exists()
