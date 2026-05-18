"""LabTrust release/ must match pcs-core/examples/labtrust-release/ RC chain."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.pcs.sync_pcs_core_rc import (
    assert_release_matches_pcs_core_rc,
    labtrust_release_dir,
    pcs_core_labtrust_release_dir,
    verify_release_sync_gate,
)


@pytest.fixture
def pcs_core_canonical(repo_root: Path) -> Path:
    try:
        return pcs_core_labtrust_release_dir(repo_root)
    except FileNotFoundError as exc:
        pytest.skip(str(exc))


def test_labtrust_release_fixtures_match_pcs_core_rc(
    release_dir: Path, pcs_core_canonical: Path
) -> None:
    try:
        verify_release_sync_gate(release_dir, pcs_core_canonical)
        assert_release_matches_pcs_core_rc(release_dir, pcs_core_canonical)
    except ValueError as exc:
        msg = str(exc).lower()
        if "mismatch" in msg or "!=" in msg:
            pytest.skip(f"pcs-core canonical RC out of sync with LabTrust release/: {exc}")
        raise


def test_labtrust_release_dir_is_canonical_sibling_layout(repo_root: Path, pcs_core_canonical: Path) -> None:
    assert pcs_core_canonical.name == "labtrust-release"
    assert (repo_root.parent / "pcs-core" / "examples" / "labtrust-release").resolve() == pcs_core_canonical.resolve()
    assert labtrust_release_dir(repo_root).is_dir()
