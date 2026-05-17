"""Shared fixtures for PCS QC-release tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.demo import run_demo


@pytest.fixture
def repo_root() -> Path:
    return get_repo_root()


@pytest.fixture
def expected_dir(repo_root: Path) -> Path:
    path = repo_root / "examples" / "pcs_qc_release" / "expected"
    if not path.is_dir():
        pytest.skip("expected/ snapshots not present")
    return path


@pytest.fixture
def valid_run(tmp_path: Path, repo_root: Path) -> Path:
    out = tmp_path / "qc-release"
    run_demo("qc-release", out_dir=out, policy_root=repo_root)
    return out


@pytest.fixture
def missing_qc_run(tmp_path: Path, repo_root: Path) -> Path:
    out = tmp_path / "missing-qc"
    run_demo("qc-release-invalid-missing-qc", out_dir=out, policy_root=repo_root)
    return out


@pytest.fixture
def unauthorized_run(tmp_path: Path, repo_root: Path) -> Path:
    out = tmp_path / "unauthorized"
    run_demo("qc-release-invalid-unauthorized", out_dir=out, policy_root=repo_root)
    return out
