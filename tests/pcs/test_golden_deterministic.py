"""Additional golden checks (release contract tests are in test_pcs_release_contract.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.validate import require_pcs_core, validate_runtime_receipt, validate_science_claim_bundle

pcs_core = pytest.importorskip("pcs_core")


def _load_golden(name: str, expected_dir: Path) -> dict:
    return json.loads((expected_dir / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "filename",
    [
        "valid_runtime_receipt.json",
        "valid_science_claim_bundle.pending.json",
        "valid_science_claim_bundle.certified.json",
        "trace_certificate.v0.json",
        "invalid_missing_qc_runtime_receipt.json",
        "invalid_unauthorized_runtime_receipt.json",
    ],
)
def test_committed_golden_validates_against_pcs_core(expected_dir: Path, filename: str) -> None:
    require_pcs_core()
    artifact = _load_golden(filename, expected_dir)
    pcs_core.validate.validate_artifact(artifact)
    if "bundle_id" in artifact:
        validate_science_claim_bundle(artifact)
    elif "receipt_id" in artifact:
        validate_runtime_receipt(artifact)
