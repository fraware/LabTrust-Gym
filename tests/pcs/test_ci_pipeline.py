"""CI export pipeline (Python source of truth for ci_validate_pcs_exports)."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.pcs.ci_pipeline import (
    run_deterministic_qc_release_export,
    validate_committed_goldens,
    validate_export_artifacts,
)
from labtrust_gym.pcs.schema_version import LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS, assert_no_legacy_pf_bundle_keys
from labtrust_gym.pcs.validate import require_pcs_core

pcs_core = pytest.importorskip("pcs_core")


def test_ci_pipeline_deterministic_export_validates_against_pcs_core(tmp_path: Path, repo_root: Path) -> None:
    require_pcs_core()
    artifacts = run_deterministic_qc_release_export(tmp_path, policy_root=repo_root)
    validate_export_artifacts(
        trace=artifacts.trace,
        receipt=artifacts.receipt,
        pending=artifacts.pending,
        certified=artifacts.certified,
    )
    pcs_core.validate.validate_artifact(artifacts.receipt)
    pcs_core.validate.validate_artifact(artifacts.pending)
    pcs_core.validate.validate_artifact(artifacts.certified)
    for legacy in LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS:
        assert legacy not in artifacts.pending
        assert legacy not in artifacts.certified


def test_committed_goldens_validate_against_pcs_core(expected_dir: Path) -> None:
    require_pcs_core()
    names = validate_committed_goldens(expected_dir)
    assert "valid_science_claim_bundle.pending.json" in names
    assert "valid_trace.json" in names


@pytest.mark.parametrize(
    "filename",
    [
        "valid_science_claim_bundle.pending.json",
        "valid_science_claim_bundle.certified.json",
    ],
)
def test_committed_golden_bundles_have_no_legacy_pf_keys(expected_dir: Path, filename: str) -> None:
    import json

    bundle = json.loads((expected_dir / filename).read_text(encoding="utf-8"))
    assert_no_legacy_pf_bundle_keys(bundle)
