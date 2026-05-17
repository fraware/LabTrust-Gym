"""Regression: canonical PCS-core bundle shape vs PF legacy top-level keys."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from labtrust_gym.pcs.attach_certificate import attach_trace_certificate
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt
from labtrust_gym.pcs.schema_version import (
    LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS,
    assert_canonical_bundle_shape,
    assert_no_legacy_pf_bundle_keys,
)
from labtrust_gym.pcs.validate import PcsValidationError, validate_science_claim_bundle

pcs_core = pytest.importorskip("pcs_core")


@pytest.mark.parametrize("legacy_key", sorted(LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS))
def test_pending_bundle_rejects_singular_runtime_receipt_shape(
    valid_run: Path, tmp_path: Path, legacy_key: str
) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    legacy = copy.deepcopy(bundle)
    if legacy_key == "runtime_receipt":
        legacy[legacy_key] = legacy.pop("runtime_receipts")[0]
    else:
        legacy[legacy_key] = {"certificate_id": "legacy-stub"}
    with pytest.raises(ValueError, match="legacy PF|runtime_receipts"):
        assert_no_legacy_pf_bundle_keys(legacy)
    with pytest.raises((ValueError, PcsValidationError)):
        validate_science_claim_bundle(legacy)


def test_exported_bundle_never_contains_legacy_pf_keys(valid_run: Path, tmp_path: Path) -> None:
    pending = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    assert_no_legacy_pf_bundle_keys(pending)
    assert_canonical_bundle_shape(pending)
    receipt = pending["runtime_receipts"][0]
    certified = attach_trace_certificate(
        pending,
        {
            "certificate_id": "cert-trace-pcs-qc-release-v0.1",
            "schema_version": "v0",
            "trace_hash": receipt["trace_hash"],
            "spec_hash": receipt["input_hashes"]["workflow"],
            "property_id": "pcs.qc_release.protocol_safety",
            "checker": "certifyedge",
            "checker_version": "0.1.0",
            "status": "CertificateChecked",
            "counterexample_ref": None,
            "created_at": receipt["ended_at"],
            "producer": "certifyedge",
            "producer_version": "0.1.0",
            "source_repo": "https://github.com/fraware/CertifyEdge",
            "source_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "signature_or_digest": "sha256:" + "b" * 64,
        },
    )
    assert_no_legacy_pf_bundle_keys(certified)
    assert "trace_certificate" not in certified
    assert "trace_certificates" not in certified
