"""PCS status transition enforcement (Phase 2 PR 4)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.export import export_pcs_bundle
from labtrust_gym.pcs.mock_certificate import build_mock_trace_certificate
from labtrust_gym.pcs.status_transitions import (
    CERTIFIED_CLAIM_STATUS,
    PENDING_CLAIM_STATUS,
    PF_VERIFIED_STATUS,
    assert_certified_bundle_claim_status,
    assert_claim_status_transition,
    assert_pending_bundle_claim_status,
    assert_verification_result_proof_checked,
    mark_bundle_stale_if_trace_diverged,
)


def test_pending_bundle_status_runtime_observed(valid_run: Path, tmp_path: Path) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert_pending_bundle_claim_status(pending)
    assert pending["claim_artifact"]["status"] == PENDING_CLAIM_STATUS


def test_certified_bundle_status_certificate_checked(valid_run: Path, tmp_path: Path) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    receipt = pending["runtime_receipts"][0]
    certified = attach_trace_certificate(pending, build_mock_trace_certificate(receipt))
    assert_certified_bundle_claim_status(certified)
    assert certified["claim_artifact"]["status"] == CERTIFIED_CLAIM_STATUS


def test_labtrust_rejects_direct_runtime_observed_to_proof_checked() -> None:
    with pytest.raises(ValueError, match="ProofChecked"):
        assert_claim_status_transition(PENDING_CLAIM_STATUS, PF_VERIFIED_STATUS)


def test_labtrust_marks_bundle_stale_if_trace_changes_after_certificate(
    valid_run: Path, tmp_path: Path
) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    receipt = pending["runtime_receipts"][0]
    certified = attach_trace_certificate(pending, build_mock_trace_certificate(receipt))

    stale = copy.deepcopy(certified)
    stale["runtime_receipts"][0]["trace_hash"] = "sha256:" + "b" * 64

    with pytest.raises(ValueError, match="Stale"):
        mark_bundle_stale_if_trace_diverged(stale)
    assert stale["claim_artifact"]["status"] == "Stale"


def test_verification_result_on_release_fixture_is_proof_checked(release_dir: Path) -> None:
    path = release_dir / "verification_result.json"
    if not path.is_file():
        pytest.skip("verification_result.json not in release fixtures")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert_verification_result_proof_checked(doc)
