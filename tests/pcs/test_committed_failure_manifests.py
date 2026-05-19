"""Committed failure gallery manifests (no regeneration)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from labtrust_gym.pcs.failure_gallery import FAILURE_CASE_MANIFEST_NAME


@pytest.fixture
def gallery_root(repo_root: Path) -> Path:
    return repo_root / "examples" / "pcs_qc_release" / "failures"


def test_gallery_index_uses_portable_paths(gallery_root: Path) -> None:
    index = json.loads((gallery_root / "gallery_index.json").read_text(encoding="utf-8"))
    assert index["out_dir"] == "failures"
    assert ":" not in index["workflow_profile"]  # no Windows drive letters
    for entry in index["cases"]:
        directory = entry["directory"]
        assert directory == entry["case_id"]
        assert "\\" not in directory
        assert not Path(directory).is_absolute()


def test_committed_gallery_has_manifest_per_case(gallery_root: Path) -> None:
    index = json.loads((gallery_root / "gallery_index.json").read_text(encoding="utf-8"))
    assert len(index["cases"]) == 12
    for entry in index["cases"]:
        case_id = entry["case_id"]
        manifest_path = gallery_root / case_id / FAILURE_CASE_MANIFEST_NAME
        assert manifest_path.is_file(), case_id
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert doc["failure_case_id"] == case_id
        assert doc["workflow_id"] == index["workflow_id"]


def test_ci_validate_failure_manifests_script(repo_root: Path) -> None:
    script = repo_root / "examples/pcs_qc_release/scripts/ci_validate_failure_manifests.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
