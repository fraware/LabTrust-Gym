"""PCS schema_version guards (v0)."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "v0"

# Provability Fabric legacy top-level keys LabTrust must never emit on ScienceClaimBundle.
LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS = frozenset(
    {
        "runtime_receipt",
        "trace_certificate",
        "trace_certificates",
    }
)

CANONICAL_BUNDLE_ARRAY_KEYS = frozenset({"runtime_receipts", "certificates"})

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


def assert_no_legacy_pf_bundle_keys(bundle: dict[str, Any]) -> None:
    """Reject PF-local legacy top-level keys on ScienceClaimBundle exports."""
    found = LEGACY_PF_BUNDLE_TOP_LEVEL_KEYS.intersection(bundle.keys())
    if found:
        keys = ", ".join(sorted(found))
        raise ValueError(
            f"ScienceClaimBundle must not contain legacy PF top-level keys: {keys}; "
            f"use {', '.join(sorted(CANONICAL_BUNDLE_ARRAY_KEYS))}"
        )


def assert_canonical_bundle_shape(bundle: dict[str, Any]) -> None:
    """ScienceClaimBundle must use PCS-core plural arrays, not PF legacy singular keys."""
    assert_no_legacy_pf_bundle_keys(bundle)
    receipts = bundle.get("runtime_receipts")
    if not isinstance(receipts, list) or len(receipts) < 1:
        raise ValueError("ScienceClaimBundle requires runtime_receipts array with at least one receipt")
    if "certificates" not in bundle or not isinstance(bundle["certificates"], list):
        raise ValueError("ScienceClaimBundle requires certificates array")


def assert_science_claim_bundle_versions(bundle: dict[str, Any]) -> None:
    assert_canonical_bundle_shape(bundle)
    assert_schema_version(bundle, path="ScienceClaimBundle")
    assert_schema_version(bundle["claim_artifact"], path="claim_artifact")
    assert_schema_version(bundle["assumption_set"], path="assumption_set")
    assert_schema_version(bundle["evidence_bundle"], path="evidence_bundle")
    for i, receipt in enumerate(bundle.get("runtime_receipts", [])):
        assert_schema_version(receipt, path=f"runtime_receipts[{i}]")
    for i, cert in enumerate(bundle.get("certificates", [])):
        assert_schema_version(cert, path=f"certificates[{i}]")
