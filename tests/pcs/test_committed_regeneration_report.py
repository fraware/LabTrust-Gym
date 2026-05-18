"""Committed regeneration_report.json (pcs-bench contract)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from labtrust_gym.pcs.regeneration_report import REGENERATION_REPORT_NAME


def test_release_has_regeneration_report(release_dir: Path) -> None:
    path = release_dir / REGENERATION_REPORT_NAME
    assert path.is_file(), (
        f"missing {REGENERATION_REPORT_NAME}; run "
        "examples/pcs_qc_release/scripts/materialize_regeneration_report.py"
    )
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["status"] == "passed"
    assert doc["workflow_id"] == "labtrust.qc_release_v0.1"
    assert doc["trace_hash"]
    assert doc["certificate_id"]
    assert doc["certified_bundle_hash"]


def test_ci_validate_regeneration_report_script(repo_root: Path) -> None:
    script = repo_root / "examples/pcs_qc_release/scripts/ci_validate_regeneration_report.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
