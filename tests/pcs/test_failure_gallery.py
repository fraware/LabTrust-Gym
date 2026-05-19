"""PCS failure gallery generation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from labtrust_gym.pcs.failure_gallery import (
    FAILURE_CASE_MANIFEST_NAME,
    demonstrate_case_failure,
    generate_failure_gallery,
    verify_failure_gallery,
)


def test_generate_failure_gallery_creates_all_cases(
    repo_root: Path, release_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / "failures"
    index = generate_failure_gallery(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
    )
    assert index["property_id"] == "hospital_lab.qc_release"
    case_ids = {c["case_id"] for c in index["cases"]}
    assert case_ids == {
        "missing_qc_result",
        "unauthorized_release",
        "trace_hash_tamper",
        "certificate_id_tamper",
        "stale_trace_after_certificate",
        "legacy_handoff_file",
        "placeholder_commit",
        "lean_trace_hash_mismatch",
        "lean_rejected_certificate",
        "lean_stale_certificate",
        "lean_signed_hash_mismatch",
        "scientific_memory_import_failure",
    }
    for case_id in case_ids:
        case_dir = out / case_id
        assert (case_dir / "README.md").is_file(), case_id
        assert (case_dir / "artifacts").is_dir(), case_id
        assert (case_dir / "expected_failure.json").is_file(), case_id
        assert (case_dir / "repair_hint.json").is_file(), case_id
        assert (case_dir / FAILURE_CASE_MANIFEST_NAME).is_file(), case_id
        meta = json.loads((case_dir / "expected_failure.json").read_text(encoding="utf-8"))
        hint = json.loads((case_dir / "repair_hint.json").read_text(encoding="utf-8"))
        manifest = json.loads((case_dir / FAILURE_CASE_MANIFEST_NAME).read_text(encoding="utf-8"))
        assert hint["hint"]
        assert meta["expected_failing_check"]
        assert manifest["failure_case_id"] == case_id
        assert manifest["expected_failure_code"] == meta["expected_failure_code"]
        assert manifest["repair_hint"] == hint["hint"]
        assert manifest["responsible_component"]


@pytest.mark.parametrize(
    "case_id",
    [
        "missing_qc_result",
        "unauthorized_release",
        "legacy_handoff_file",
        "trace_hash_tamper",
        "stale_trace_after_certificate",
        "certificate_id_tamper",
        "placeholder_commit",
    ],
)
def test_failure_gallery_cases_fail_expected_check(
    repo_root: Path, release_dir: Path, tmp_path: Path, case_id: str
) -> None:
    out = tmp_path / "gallery"
    generate_failure_gallery(
        out,
        workflow_key="qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
    )
    label = demonstrate_case_failure(out / case_id, policy_root=repo_root)
    meta = json.loads((out / case_id / "expected_failure.json").read_text(encoding="utf-8"))
    assert label == meta["expected_failing_check"]


def test_verify_failure_gallery_index(repo_root: Path, release_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "gallery"
    generate_failure_gallery(
        out,
        workflow_key="hospital_lab.qc_release",
        policy_root=repo_root,
        release_dir=release_dir,
    )
    checks = verify_failure_gallery(out, policy_root=repo_root)
    assert len(checks) >= 12


def test_generate_failure_gallery_cli(repo_root: Path, release_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "failures"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "generate-failure-gallery",
            "--workflow",
            "hospital_lab.qc_release",
            "--out",
            str(out),
            "--release-dir",
            str(release_dir),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (out / "gallery_index.json").is_file()
