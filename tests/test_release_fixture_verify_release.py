"""
Release fixture is the canonical regression anchor for verify-release.

The fixture at tests/fixtures/release_fixture_minimal is built once from a known commit via:
  scripts/build_release_fixture.sh

Any change that breaks release invariants fails this test, even if the golden suite passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.export.verify import (
    RELEASE_MANIFEST_FILENAME,
    RISK_REGISTER_BUNDLE_FILENAME,
    discover_evidence_bundles,
    verify_release,
)


def _release_fixture_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "release_fixture_minimal"


def _fixture_available() -> bool:
    d = _release_fixture_dir()
    if not d.is_dir():
        return False
    # Must have at least one evidence bundle and risk register (or manifest) for verify-release to be meaningful
    bundles = discover_evidence_bundles(d)
    has_bundle = len(bundles) > 0
    has_risk = (d / RISK_REGISTER_BUNDLE_FILENAME).exists()
    has_manifest = (d / RELEASE_MANIFEST_FILENAME).exists()
    return has_bundle and (has_risk or has_manifest)


@pytest.mark.skipif(
    not _fixture_available(),
    reason="Release fixture not present. Run scripts/build_release_fixture.sh and commit tests/fixtures/release_fixture_minimal/",
)
def test_release_fixture_verify_release() -> None:
    """verify-release --strict-fingerprints must pass on the committed release fixture (release chain regression anchor)."""
    repo_root = Path(__file__).resolve().parent.parent
    release_dir = _release_fixture_dir()
    all_passed, results, release_errors = verify_release(
        release_dir,
        policy_root=repo_root,
        allow_extra_files=False,
        quiet=False,
        strict_fingerprints=True,
    )
    if release_errors:
        raise AssertionError(f"verify-release failed: {release_errors}")
    for bundle_path, passed, report, errors in results:
        if not passed:
            raise AssertionError(f"Bundle {bundle_path} failed: {report}; errors: {errors}")
    assert all_passed, "verify-release did not pass"
