"""PCS policy YAML structural validation."""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.pcs.policy_validate import validate_pcs_policy_files


def test_pcs_policy_files_valid(repo_root: Path) -> None:
    assert validate_pcs_policy_files(repo_root) == []
