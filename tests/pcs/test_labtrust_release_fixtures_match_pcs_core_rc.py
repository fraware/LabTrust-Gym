"""LabTrust release/ must match pcs-core/examples/labtrust-release/ RC chain."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.pcs.sync_pcs_core_rc import (
    assert_release_matches_pcs_core_rc,
    extract_rc_chain_identity,
    labtrust_release_dir,
    pcs_core_labtrust_release_dir,
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
    identity = assert_release_matches_pcs_core_rc(release_dir, pcs_core_canonical)
    canonical = extract_rc_chain_identity(pcs_core_canonical)

    assert identity["trace_hash"] == canonical["trace_hash"]
    assert identity["certificate_id"] == canonical["certificate_id"]
    assert identity["certified_bundle_hash"] == canonical["certified_bundle_hash"]
    assert identity["labtrust_gym_commit"] == canonical["labtrust_gym_commit"]
    assert identity["certifyedge_commit"] == canonical["certifyedge_commit"]

    assert identity["certificate_id"] == "cert-trace-886c95f0-5d63-42d6-aa13-5891c12c5a6a"
    assert identity["trace_hash"] == "sha256:c3e8a3dc4ad86d533de1dfa4ae7fe2a338c2cff3c945404c96a75216524d58cd"
    assert identity["certified_bundle_hash"] == (
        "sha256:9b42d792199eb6f358d26f822699f0ed65bb4366eee306d4958d42121c656833"
    )
    assert identity["labtrust_gym_commit"] == "4c5439ae358733f9a4c4a58e33fdaed1ab0d29de"
    assert identity["certifyedge_commit"] == "cb6848001e2e60a484e04eba5ad6be3fe2e4eccc"


def test_labtrust_release_dir_is_canonical_sibling_layout(repo_root: Path, pcs_core_canonical: Path) -> None:
    assert pcs_core_canonical.name == "labtrust-release"
    assert (repo_root.parent / "pcs-core" / "examples" / "labtrust-release").resolve() == pcs_core_canonical.resolve()
    assert labtrust_release_dir(repo_root).is_dir()
