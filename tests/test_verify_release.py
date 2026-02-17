"""
Tests for verify-release: discover EvidenceBundles under a release and verify all.
"""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.export.receipts import (
    build_receipts_from_log,
    load_episode_log,
    write_evidence_bundle,
)
from labtrust_gym.export.verify import (
    EVIDENCE_BUNDLE_DIRNAME,
    RELEASE_MANIFEST_FILENAME,
    build_release_manifest,
    discover_evidence_bundles,
    verify_release,
    verify_release_manifest,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _tiny_episode_log(tmp_path: Path) -> Path:
    """Write a minimal episode log (JSONL) and return path."""
    entries = [
        {
            "t_s": 100,
            "agent_id": "A",
            "action_type": "CREATE_ACCESSION",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h0", "length": 1, "last_event_hash": "e0"},
        },
        {
            "t_s": 200,
            "agent_id": "A",
            "action_type": "ACCEPT_SPECIMEN",
            "args": {"specimen_id": "S1"},
            "status": "ACCEPTED",
            "hashchain": {"head_hash": "h1", "length": 2, "last_event_hash": "e1"},
        },
    ]
    log_path = tmp_path / "ep.jsonl"
    with log_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, sort_keys=True) + "\n")
    return log_path


def test_discover_evidence_bundles_empty(tmp_path: Path) -> None:
    """No receipts dir -> no bundles."""
    assert discover_evidence_bundles(tmp_path) == []


def test_discover_evidence_bundles_no_receipts(tmp_path: Path) -> None:
    """receipts/ exists but empty -> no bundles."""
    (tmp_path / "receipts").mkdir()
    assert discover_evidence_bundles(tmp_path) == []


def test_discover_evidence_bundles_one_bundle(tmp_path: Path) -> None:
    """One valid EvidenceBundle.v0.1 under receipts/cond_0/ -> discovered."""
    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "bundle_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint="fp_test",
        partner_id=None,
    )
    release_dir = tmp_path / "release"
    dest_bundle = release_dir / "receipts" / "cond_0" / EVIDENCE_BUNDLE_DIRNAME
    dest_bundle.mkdir(parents=True, exist_ok=True)
    for f in bundle_dir.iterdir():
        if f.is_file():
            (dest_bundle / f.name).write_bytes(f.read_bytes())
    bundles = discover_evidence_bundles(release_dir)
    assert len(bundles) == 1
    assert bundles[0] == dest_bundle
    assert (bundles[0] / "manifest.json").exists()


def test_verify_release_one_valid_bundle(tmp_path: Path) -> None:
    """verify_release on a release dir with one valid EvidenceBundle -> all passed."""
    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "bundle_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint="fp_test",
        partner_id=None,
    )
    release_dir = tmp_path / "release"
    (release_dir / "receipts" / "cond_0" / EVIDENCE_BUNDLE_DIRNAME).mkdir(
        parents=True, exist_ok=True
    )
    dest_bundle = release_dir / "receipts" / "cond_0" / EVIDENCE_BUNDLE_DIRNAME
    for f in bundle_dir.iterdir():
        if f.is_file():
            (dest_bundle / f.name).write_bytes(f.read_bytes())
    all_passed, results, release_errors = verify_release(
        release_dir,
        policy_root=root,
        allow_extra_files=False,
    )
    assert all_passed
    assert len(release_errors) == 0
    assert len(results) == 1
    path, passed, report, errors = results[0]
    assert passed
    assert path == dest_bundle
    assert "PASS" in report
    assert len(errors) == 0


def test_verify_release_no_bundles(tmp_path: Path) -> None:
    """verify_release on dir with no receipts -> vacuous pass (caller should check discover first)."""
    all_passed, results, release_errors = verify_release(
        tmp_path,
        policy_root=_repo_root(),
    )
    assert results == []
    assert all_passed  # vacuous: no bundle failed
    assert isinstance(release_errors, list)


def test_verify_release_cli_no_bundles(tmp_path: Path) -> None:
    """CLI verify-release with no EvidenceBundles -> exit 1 and message."""
    import subprocess
    import sys

    (tmp_path / "receipts").mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "verify-release",
            "--release-dir",
            str(tmp_path),
        ],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "No EvidenceBundle.v0.1" in proc.stderr or "No EvidenceBundle" in proc.stdout


def test_verify_release_cli_one_valid_bundle(tmp_path: Path) -> None:
    """CLI verify-release with one valid bundle -> exit 0."""
    import subprocess
    import sys

    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "bundle_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint="fp_test",
        partner_id=None,
    )
    release_dir = tmp_path / "release"
    (release_dir / "receipts" / "cond_0" / EVIDENCE_BUNDLE_DIRNAME).mkdir(
        parents=True, exist_ok=True
    )
    dest_bundle = release_dir / "receipts" / "cond_0" / EVIDENCE_BUNDLE_DIRNAME
    for f in bundle_dir.iterdir():
        if f.is_file():
            (dest_bundle / f.name).write_bytes(f.read_bytes())
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "verify-release",
            "--release-dir",
            str(release_dir),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout} stderr={proc.stderr}"
    assert "all passed" in proc.stdout or "PASS" in proc.stdout


def test_build_and_verify_release_manifest(tmp_path: Path) -> None:
    """build_release_manifest writes RELEASE_MANIFEST; verify_release_manifest passes when hashes match."""
    root = _repo_root()
    log_path = _tiny_episode_log(tmp_path)
    entries = load_episode_log(log_path)
    receipts = build_receipts_from_log(entries)
    out_dir = tmp_path / "bundle_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = write_evidence_bundle(
        out_dir,
        receipts,
        entries,
        policy_fingerprint="fp_test",
        partner_id=None,
    )
    release_dir = tmp_path / "release"
    (release_dir / "receipts" / "cond_0" / EVIDENCE_BUNDLE_DIRNAME).mkdir(parents=True, exist_ok=True)
    dest_bundle = release_dir / "receipts" / "cond_0" / EVIDENCE_BUNDLE_DIRNAME
    for f in bundle_dir.iterdir():
        if f.is_file():
            (dest_bundle / f.name).write_bytes(f.read_bytes())
    (release_dir / "MANIFEST.v0.1.json").write_text('{"version":"0.1","files":[]}', encoding="utf-8")
    manifest_path = build_release_manifest(release_dir, policy_root=root)
    assert manifest_path.exists()
    assert manifest_path.name == RELEASE_MANIFEST_FILENAME
    errors = verify_release_manifest(release_dir)
    assert len(errors) == 0
    all_passed, results, release_errors = verify_release(release_dir, policy_root=root)
    assert len(release_errors) == 0
    assert all_passed


def test_build_release_manifest_determinism(tmp_path: Path) -> None:
    """Same release dir -> two build-release-manifest runs produce identical RELEASE_MANIFEST."""
    root = _repo_root()
    release_dir = tmp_path / "release"
    release_dir.mkdir(parents=True)
    (release_dir / "receipts").mkdir(parents=True)
    (release_dir / "metadata.json").write_text('{"profile":"minimal"}', encoding="utf-8")
    manifest_path1 = build_release_manifest(release_dir, policy_root=root)
    manifest_path2 = build_release_manifest(release_dir, policy_root=root)
    assert manifest_path1.exists() and manifest_path2.exists()
    c1 = manifest_path1.read_bytes()
    c2 = manifest_path2.read_bytes()
    assert c1 == c2, "Two build-release-manifest runs on same dir must yield identical RELEASE_MANIFEST"
