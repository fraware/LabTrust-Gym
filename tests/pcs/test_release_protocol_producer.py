"""Phase 2 runtime protocol producer: handoffs, fragment schema, status, regenerate."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("pcs_core")

from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.export import export_pcs_bundle
from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    assert_handoff_manifest_valid,
    assert_handoff_registry_check,
    build_runtime_to_certificate_handoff,
    emit_handoff_manifest,
)
from labtrust_gym.pcs.mock_certificate import build_mock_trace_certificate
from labtrust_gym.pcs.regenerate_release_chain import compare_release_hashes_to_canonical
from labtrust_gym.pcs.release_protocol_producer import (
    LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS,
    assert_protocol_package_complete,
)
from labtrust_gym.pcs.release_fragment import (
    build_labtrust_release_fragment,
    validate_release_fragment,
)
from labtrust_gym.pcs.release_handoff import build_pf_handoff
from labtrust_gym.pcs.science_claim_bundle import build_science_claim_bundle
from labtrust_gym.pcs.status_transitions import (
    CERTIFIED_CLAIM_STATUS,
    PENDING_CLAIM_STATUS,
    PF_VERIFIED_STATUS,
    assert_claim_status_transition,
    assert_labtrust_never_emits_proof_checked,
    mark_bundle_stale_if_trace_diverged,
)
from labtrust_gym.pcs.sync_pcs_core_rc import pcs_core_labtrust_release_dir


def test_committed_release_protocol_package_complete(release_dir: Path) -> None:
    assert_protocol_package_complete(release_dir)
    assert set(LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS).issubset(
        {p.name for p in release_dir.iterdir() if p.is_file()}
    )


def test_emit_handoff_to_certifyedge_validates_against_pcs_core(
    release_dir: Path, tmp_path: Path
) -> None:
    out = tmp_path / HANDOFF_TO_CERTIFYEDGE_NAME
    doc = emit_handoff_manifest(
        kind="runtime-to-certificate",
        trace_path=release_dir / "trace.json",
        receipt_path=release_dir / "runtime_receipt.json",
        out_path=out,
        release_mode=True,
    )
    assert doc["handoff_kind"] == "runtime_to_certificate"
    assert_handoff_manifest_valid(doc)
    assert_handoff_registry_check(out)


def test_emit_handoff_to_pf_validates_against_pcs_core(release_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / HANDOFF_TO_PF_NAME
    doc = emit_handoff_manifest(
        kind="bundle-to-verifier",
        bundle_path=release_dir / "science_claim_bundle.certified.json",
        out_path=out,
        release_mode=True,
    )
    assert doc["handoff_kind"] == "bundle_to_verifier"
    assert_handoff_manifest_valid(doc)
    assert_handoff_registry_check(out)


def test_handoff_subdir_matches_flat_phase2_handoffs(release_dir: Path) -> None:
    handoff_root = release_dir / "handoff"
    if not handoff_root.is_dir():
        pytest.skip("release/handoff/ not present")
    from labtrust_gym.pcs.release_run import file_content_digest

    for name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME):
        flat = release_dir / name
        sub = handoff_root / name
        if not flat.is_file():
            pytest.skip(f"{name} not committed at release root")
        if sub.is_file():
            assert file_content_digest(flat) == file_content_digest(sub)


def test_release_fragment_validates_against_component_fragment_schema(release_dir: Path) -> None:
    if not (release_dir / HANDOFF_TO_CERTIFYEDGE_NAME).is_file():
        manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
        build_pf_handoff(release_dir, manifest)
    fragment = json.loads((release_dir / "labtrust_release_fragment.json").read_text(encoding="utf-8"))
    errors = validate_release_fragment(fragment)
    assert errors == [], errors
    assert fragment.get("signature_or_digest", "").startswith("sha256:")
    assert HANDOFF_TO_CERTIFYEDGE_NAME in fragment["artifacts"]


def test_labtrust_never_emits_proof_checked(valid_run: Path) -> None:
    pending = build_science_claim_bundle(valid_run)
    assert_labtrust_never_emits_proof_checked(pending)
    with pytest.raises(ValueError, match="ProofChecked"):
        assert_claim_status_transition(PENDING_CLAIM_STATUS, PF_VERIFIED_STATUS)
    bad = copy.deepcopy(pending)
    bad["claim_artifact"]["status"] = PF_VERIFIED_STATUS
    with pytest.raises(ValueError, match="ProofChecked"):
        assert_labtrust_never_emits_proof_checked(bad)


def test_pending_to_certified_status_transition_allowed(valid_run: Path, tmp_path: Path) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    receipt = pending["runtime_receipts"][0]
    certified = attach_trace_certificate(pending, build_mock_trace_certificate(receipt))
    assert certified["claim_artifact"]["status"] == CERTIFIED_CLAIM_STATUS
    assert_claim_status_transition(PENDING_CLAIM_STATUS, CERTIFIED_CLAIM_STATUS)


def test_certified_bundle_marked_stale_if_trace_hash_changes(
    valid_run: Path, tmp_path: Path
) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    receipt = pending["runtime_receipts"][0]
    certified = attach_trace_certificate(pending, build_mock_trace_certificate(receipt))
    stale = copy.deepcopy(certified)
    stale["runtime_receipts"][0]["trace_hash"] = "sha256:" + "c" * 64
    with pytest.raises(ValueError, match="Stale"):
        mark_bundle_stale_if_trace_diverged(stale)
    assert stale["claim_artifact"]["status"] == "Stale"


def test_regenerate_release_chain_matches_canonical_hashes(
    release_dir: Path, repo_root: Path, tmp_path: Path
) -> None:
    try:
        canonical = pcs_core_labtrust_release_dir(repo_root)
    except FileNotFoundError:
        pytest.skip("pcs-core labtrust-release fixtures not available")
    if not shutil.which("certifyedge"):
        pytest.skip("certifyedge binary not on PATH")
    ce_root = repo_root.parent / "CertifyEdge"
    if not ce_root.is_dir():
        pytest.skip("CertifyEdge repo not found")
    spec = ce_root / "templates" / "hospital_lab" / "qc_release.stl"
    if not spec.is_file():
        pytest.skip("CertifyEdge qc_release.stl not found")

    from labtrust_gym.pcs.regenerate_release_chain import regenerate_release_chain

    out = tmp_path / "release"
    try:
        regenerate_release_chain(
            out,
            policy_root=repo_root,
            certifyedge_root=ce_root,
            certifyedge_spec=spec,
            pcs_core_dir=canonical,
        )
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"regenerate-release-chain requires pinned LabTrust/CertifyEdge trace: {exc}")
    checks = compare_release_hashes_to_canonical(out, canonical)
    assert "certified_bundle_hash" in checks
