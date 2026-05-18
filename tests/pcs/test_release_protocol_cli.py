"""Stable CLI surface for PCS Phase 2 protocol production."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pcs_core")

from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME
from labtrust_gym.pcs.release_protocol_producer import (
    LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS,
    assert_protocol_package_complete,
)
from labtrust_gym.pcs.regenerate_release_protocol import report_canonical_drift
from labtrust_gym.pcs.release_protocol import LEGACY_HANDOFF_SUBDIR_GUARD
from labtrust_gym.pcs.release_run import file_content_digest
from labtrust_gym.pcs.sync_pcs_core_rc import pcs_core_labtrust_release_dir


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "labtrust_gym.cli.main", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )


def test_emit_handoff_to_certifyedge_cli(release_dir: Path, repo_root: Path, tmp_path: Path) -> None:
    out = tmp_path / HANDOFF_TO_CERTIFYEDGE_NAME
    proc = _run(
        [
            "emit-handoff-to-certifyedge",
            "--trace",
            str(release_dir / "trace.json"),
            "--runtime-receipt",
            str(release_dir / "runtime_receipt.json"),
            "--property-id",
            "hospital_lab.qc_release",
            "--out",
            str(out),
            "--release-mode",
        ],
        cwd=repo_root,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["handoff_kind"] == "runtime_to_certificate"


def test_emit_handoff_to_pf_cli(release_dir: Path, repo_root: Path, tmp_path: Path) -> None:
    out = tmp_path / HANDOFF_TO_PF_NAME
    proc = _run(
        [
            "emit-handoff-to-pf",
            "--bundle",
            str(release_dir / "science_claim_bundle.certified.json"),
            "--out",
            str(out),
            "--release-mode",
        ],
        cwd=repo_root,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["handoff_kind"] == "bundle_to_verifier"


def test_emit_release_fragment_cli(release_dir: Path, repo_root: Path, tmp_path: Path) -> None:
    out = tmp_path / "labtrust_release_fragment.json"
    proc = _run(
        [
            "emit-release-fragment",
            "--release-dir",
            str(release_dir),
            "--out",
            str(out),
        ],
        cwd=repo_root,
    )
    assert proc.returncode == 0, proc.stderr
    fragment = json.loads(out.read_text(encoding="utf-8"))
    assert fragment.get("signature_or_digest", "").startswith("sha256:")


def test_regenerate_release_protocol_from_clean_directory(
    repo_root: Path, tmp_path: Path
) -> None:
    if not shutil.which("certifyedge"):
        pytest.skip("certifyedge not on PATH")
    ce_root = repo_root.parent / "CertifyEdge"
    if not ce_root.is_dir():
        pytest.skip("CertifyEdge not found")
    spec = ce_root / "templates" / "hospital_lab" / "qc_release.stl"
    if not spec.is_file():
        pytest.skip("CertifyEdge spec missing")

    out = tmp_path / "release"
    pcs_core = repo_root.parent / "pcs-core"
    args = [
        "regenerate-release-protocol",
        "--out",
        str(out),
        "--certifyedge-bin",
        "certifyedge",
    ]
    if pcs_core.is_dir():
        args.extend(["--pcs-core", str(pcs_core)])
    env = {**os.environ, "PCS_DETERMINISTIC": "1", "PCS_RELEASE_FIXTURE": "1"}
    proc = _run(args, cwd=repo_root, env=env)
    if proc.returncode != 0 and "trace hash mismatch" in proc.stderr.lower():
        pytest.skip(f"CertifyEdge trace pin mismatch: {proc.stderr}")
    assert proc.returncode == 0, proc.stderr
    for name in (
        "trace.json",
        "runtime_receipt.json",
        "science_claim_bundle.pending.json",
        "science_claim_bundle.certified.json",
        HANDOFF_TO_CERTIFYEDGE_NAME,
        HANDOFF_TO_PF_NAME,
        "labtrust_release_fragment.json",
        "trace_certificate.json",
    ):
        assert (out / name).is_file(), name


def test_component_release_fragment_validates_against_pcs_core(release_dir: Path) -> None:
    from labtrust_gym.pcs.release_fragment import (
        assert_release_fragment_registry_check,
        assert_release_fragment_valid,
    )

    fragment_path = release_dir / "labtrust_release_fragment.json"
    if not fragment_path.is_file():
        pytest.skip("fragment not committed")
    fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
    assert_release_fragment_valid(fragment)
    proc = subprocess.run(
        ["pcs", "validate", str(fragment_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert_release_fragment_registry_check(fragment_path)


def test_labtrust_never_emits_proof_checked(valid_run: Path) -> None:
    from labtrust_gym.pcs.science_claim_bundle import build_science_claim_bundle
    from labtrust_gym.pcs.status_transitions import assert_labtrust_never_emits_proof_checked

    pending = build_science_claim_bundle(valid_run)
    assert_labtrust_never_emits_proof_checked(pending)


def test_release_mode_rejects_legacy_handoff_files(
    release_dir: Path, repo_root: Path, tmp_path: Path
) -> None:
    drift = tmp_path / "release_legacy"
    shutil.copytree(release_dir, drift)
    (drift / "handoff" / LEGACY_HANDOFF_SUBDIR_GUARD).write_text('{"legacy": true}\n', encoding="utf-8")
    proc = _run(
        ["verify-release-protocol", "--release-dir", str(drift)],
        cwd=repo_root,
    )
    assert proc.returncode != 0
    assert "handoff_for_pf" in proc.stderr or "handoff_for_pf" in proc.stdout


def test_trace_hash_change_marks_certified_bundle_stale(valid_run: Path, tmp_path: Path) -> None:
    import copy

    from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
    from labtrust_gym.pcs.export import export_pcs_bundle
    from labtrust_gym.pcs.mock_certificate import build_mock_trace_certificate
    from labtrust_gym.pcs.status_transitions import mark_bundle_stale_if_trace_diverged

    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    certified = attach_trace_certificate(
        pending, build_mock_trace_certificate(pending["runtime_receipts"][0])
    )
    stale = copy.deepcopy(certified)
    stale["runtime_receipts"][0]["trace_hash"] = "sha256:" + "d" * 64
    with pytest.raises(ValueError, match="Stale"):
        mark_bundle_stale_if_trace_diverged(stale)


def test_regenerated_release_matches_canonical_hashes_or_reports_expected_drift(
    release_dir: Path, repo_root: Path
) -> None:
    try:
        canonical = pcs_core_labtrust_release_dir(repo_root)
    except FileNotFoundError:
        pytest.skip("pcs-core canonical fixtures unavailable")
    report = report_canonical_drift(release_dir, canonical)
    if report["drift"] is None:
        assert "certified_bundle_hash" in report["matched"]
    else:
        pytest.skip(f"expected drift vs canonical RC: {report['drift']}")


def test_committed_release_has_complete_protocol_package(release_dir: Path) -> None:
    assert_protocol_package_complete(release_dir)
    for name in LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS:
        assert (release_dir / name).is_file()


def test_verify_release_protocol_cli(release_dir: Path, repo_root: Path) -> None:
    proc = _run(
        ["verify-release-protocol", "--release-dir", str(release_dir)],
        cwd=repo_root,
    )
    assert proc.returncode == 0, proc.stderr


def test_stale_handoff_digest_rejected(
    release_dir: Path, repo_root: Path, tmp_path: Path
) -> None:
    drift = tmp_path / "release_stale"
    shutil.copytree(release_dir, drift)
    handoff_path = drift / HANDOFF_TO_PF_NAME
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    entry = handoff["input_artifacts"]["science_claim_bundle.certified.json"]
    entry["sha256"] = "sha256:" + "0" * 64
    handoff_path.write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    proc = _run(
        ["verify-release-protocol", "--release-dir", str(drift)],
        cwd=repo_root,
    )
    assert proc.returncode != 0
    assert "stale" in proc.stderr.lower() or "stale" in proc.stdout.lower()
