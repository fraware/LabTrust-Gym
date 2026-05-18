"""LabTrust release status-policy checks."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from labtrust_gym.pcs.export import export_pcs_bundle
from labtrust_gym.pcs.status_policy import assert_release_bundle_status_policy, check_release_status_policy
from labtrust_gym.pcs.status_transitions import PF_VERIFIED_STATUS


def test_check_status_policy_passes_on_release_fixtures(release_dir: Path) -> None:
    result = check_release_status_policy(release_dir)
    assert result["status"] == "passed"
    assert "pending_status_runtime_observed" in result["checks"]


def test_check_status_policy_cli(release_dir: Path, repo_root: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "check-status-policy",
            "--release-dir",
            str(release_dir),
            "--json",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["status"] == "passed"


def test_release_status_policy_rejects_proof_checked_on_pending(
    valid_run: Path, tmp_path: Path
) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    (tmp_path / "science_claim_bundle.pending.json").write_text(
        json.dumps(pending, indent=2) + "\n",
        encoding="utf-8",
    )
    certified = copy.deepcopy(pending)
    certified["claim_artifact"]["status"] = "CertificateChecked"
    (tmp_path / "science_claim_bundle.certified.json").write_text(
        json.dumps(certified, indent=2) + "\n",
        encoding="utf-8",
    )
    bad = copy.deepcopy(pending)
    bad["claim_artifact"]["status"] = PF_VERIFIED_STATUS
    (tmp_path / "science_claim_bundle.pending.json").write_text(
        json.dumps(bad, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ProofChecked"):
        assert_release_bundle_status_policy(tmp_path)
