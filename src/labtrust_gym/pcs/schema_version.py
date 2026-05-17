"""PCS schema_version guards (v0)."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "v0"

PCS_ARTIFACTS_WITH_SCHEMA_VERSION = (
    "RuntimeReceipt.v0",
    "AssumptionSet.v0",
    "ClaimArtifact.v0",
    "EvidenceBundle.v0",
    "ScienceClaimBundle.v0",
)


def assert_schema_version(
    artifact: dict[str, Any],
    *,
    expected: str = SCHEMA_VERSION,
    path: str = "root",
) -> None:
    actual = artifact.get("schema_version")
    if actual != expected:
        raise ValueError(f"{path}: schema_version must be {expected!r}, got {actual!r}")


def assert_science_claim_bundle_versions(bundle: dict[str, Any]) -> None:
    assert_schema_version(bundle, path="ScienceClaimBundle")
    assert_schema_version(bundle["claim_artifact"], path="claim_artifact")
    assert_schema_version(bundle["assumption_set"], path="assumption_set")
    assert_schema_version(bundle["evidence_bundle"], path="evidence_bundle")
    for i, receipt in enumerate(bundle.get("runtime_receipts", [])):
        assert_schema_version(receipt, path=f"runtime_receipts[{i}]")
    for i, cert in enumerate(bundle.get("certificates", [])):
        assert_schema_version(cert, path=f"certificates[{i}]")
