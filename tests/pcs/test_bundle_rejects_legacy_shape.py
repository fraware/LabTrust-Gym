"""Reject PF legacy singular runtime_receipt on ScienceClaimBundle."""

from __future__ import annotations

import copy

import pytest

from labtrust_gym.pcs.export import export_pcs_bundle
from labtrust_gym.pcs.schema_version import assert_canonical_bundle_shape
from labtrust_gym.pcs.validate import PcsValidationError, validate_science_claim_bundle

pytest.importorskip("pcs_core")


def test_bundle_with_singular_runtime_receipt_fails_canonical_check(valid_run, tmp_path) -> None:
    bundle = export_pcs_bundle(valid_run, tmp_path / "pending.json")
    legacy = copy.deepcopy(bundle)
    legacy["runtime_receipt"] = legacy.pop("runtime_receipts")[0]
    with pytest.raises(ValueError, match="runtime_receipt"):
        assert_canonical_bundle_shape(legacy)
    with pytest.raises((ValueError, PcsValidationError)):
        validate_science_claim_bundle(legacy)
