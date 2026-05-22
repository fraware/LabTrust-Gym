"""Offline fixture for PcsBenchIngest.v0 producer gate."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.bench_schemas import validate_producer_ingest_contract
from labtrust_gym.pcs.workflow_profile import CANONICAL_QC_RELEASE_WORKFLOW_ID

FIXTURE = Path("tests/fixtures/pcs_bench_ingest/labtrust/pcs_bench_ingest.v0.json")


def test_pcs_bench_ingest_fixture_validates(repo_root: Path) -> None:
    path = repo_root / FIXTURE
    if not path.is_file():
        import pytest

        pytest.skip("run scripts/generate_pcs_bench_ingest_fixture.py to create fixture")
    doc = json.loads(path.read_text(encoding="utf-8"))
    checks = validate_producer_ingest_contract(
        doc, ingest_path=path, policy_root=repo_root, pcs_core_root=None
    )
    assert "pcs_bench_ingest.workflow_id" in checks
    assert doc["workflow_id"] == CANONICAL_QC_RELEASE_WORKFLOW_ID


def test_canonical_workflow_id_from_alias(repo_root: Path) -> None:
    from labtrust_gym.pcs.workflow_profile import canonical_workflow_property_id, workflow_profile_view

    profile = workflow_profile_view(policy_root=repo_root)
    assert canonical_workflow_property_id("qc-release", profile=profile) == CANONICAL_QC_RELEASE_WORKFLOW_ID
    assert canonical_workflow_property_id("hospital_lab.qc_release", profile=profile) == (
        CANONICAL_QC_RELEASE_WORKFLOW_ID
    )
