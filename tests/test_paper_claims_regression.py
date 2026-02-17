"""
Paper claims regression: build minimal paper artifact, extract snapshot, compare to committed snapshot.

Run with LABTRUST_PAPER_SMOKE=1 and fixed seed so output is deterministic. Committed snapshot at
tests/fixtures/paper_claims_snapshot/v0.1/ must have been generated from the same pipeline; update via
  labtrust package-release --profile paper_v0.1 --out <dir> --seed-base 42
  (with LABTRUST_PAPER_SMOKE=1)
  python scripts/extract_paper_claims_snapshot.py <dir> --out tests/fixtures/paper_claims_snapshot/v0.1
  then commit the fixture.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Snapshot dir (committed)
REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = REPO_ROOT / "tests" / "fixtures" / "paper_claims_snapshot" / "v0.1"


@pytest.mark.slow
def test_paper_claims_regression_against_committed_snapshot(tmp_path: Path) -> None:
    """Build paper release (smoke), extract snapshot, compare to committed snapshot."""
    if not (SNAPSHOT_DIR / "snapshot_manifest.json").exists():
        pytest.skip(
            "Committed snapshot missing: run extract_paper_claims_snapshot and "
            "commit tests/fixtures/paper_claims_snapshot/v0.1"
        )

    from labtrust_gym.studies.package_release import run_package_release_paper
    from labtrust_gym.studies.paper_claims_compare import compare_paper_snapshot

    release_dir = tmp_path / "paper_release"
    prev = os.environ.get("LABTRUST_PAPER_SMOKE")
    try:
        os.environ["LABTRUST_PAPER_SMOKE"] = "1"
        run_package_release_paper(
            out_dir=release_dir,
            repo_root=REPO_ROOT,
            seed_base=42,
            fixed_timestamp="2025-01-01T00:00:00Z",
        )
    finally:
        if prev is not None:
            os.environ["LABTRUST_PAPER_SMOKE"] = prev
        else:
            os.environ.pop("LABTRUST_PAPER_SMOKE", None)

    # SECURITY/coverage.json can contain non-deterministic fields (paths, timestamps)
    passed, report = compare_paper_snapshot(
        release_dir, SNAPSHOT_DIR, optional_keys={"coverage"}
    )
    if not passed:
        raise AssertionError("Paper claims snapshot regression:\n" + "\n".join(report))


def test_compare_manifests_in_memory() -> None:
    """Lock in compare_manifests logic with two in-memory manifests (no package_release or disk)."""
    from labtrust_gym.studies.paper_claims_compare import compare_manifests

    # Identical manifests -> pass
    manifest = {
        "version": "v0.1",
        "entries": [
            {"key": "summary", "path": "TABLES/summary", "sha256": "a" * 64},
            {"key": "safety_case", "path": "SAFETY_CASE/safety_case.json", "sha256": "b" * 64},
        ],
    }
    passed, report = compare_manifests(manifest, manifest)
    assert passed
    assert not any("missing" in r or "mismatch" in r for r in report)

    # Missing key in actual -> fail
    expected = {"entries": [{"key": "x", "path": "x", "sha256": "c" * 64}]}
    actual = {"entries": []}
    passed, report = compare_manifests(expected, actual)
    assert not passed
    assert any("missing in actual manifest" in r for r in report)

    # Present vs absent mismatch -> fail
    expected = {"entries": [{"key": "y", "path": "y", "status": "absent"}]}
    actual = {"entries": [{"key": "y", "path": "y", "sha256": "d" * 64}]}
    passed, report = compare_manifests(expected, actual)
    assert not passed
    assert any("expected absent" in r and "actual present" in r for r in report)

    # sha256 mismatch -> fail
    expected = {"entries": [{"key": "z", "path": "z", "sha256": "e" * 64}]}
    actual = {"entries": [{"key": "z", "path": "z", "sha256": "f" * 64}]}
    passed, report = compare_manifests(expected, actual)
    assert not passed
    assert any("sha256 mismatch" in r for r in report)

    # optional_keys: sha256 mismatch for optional key -> pass (reported but not failing)
    expected = {"entries": [{"key": "cov", "path": "SECURITY/coverage.json", "sha256": "g" * 64}]}
    actual = {"entries": [{"key": "cov", "path": "SECURITY/coverage.json", "sha256": "h" * 64}]}
    passed, report = compare_manifests(expected, actual, optional_keys={"cov"})
    assert passed
    assert any("optional, not failing" in r for r in report)

    # risk_bundle by_status within tolerance -> pass
    exp_entries = [
        {"key": "risk_bundle", "path": "r", "sha256": "i" * 64, "by_status": {"open": 2, "closed": 1}},
    ]
    act_entries = [
        {"key": "risk_bundle", "path": "r", "sha256": "i" * 64, "by_status": {"open": 3, "closed": 1}},
    ]
    passed, report = compare_manifests(
        {"entries": exp_entries},
        {"entries": act_entries},
        allow_by_status_delta=True,
        by_status_max_delta=1,
    )
    assert passed

    # risk_bundle by_status delta exceeding max -> fail
    passed, report = compare_manifests(
        {"entries": exp_entries},
        {"entries": act_entries},
        allow_by_status_delta=True,
        by_status_max_delta=0,
    )
    assert not passed
    assert any("by_status" in r for r in report)
