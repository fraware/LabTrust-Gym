"""Proof-obligation readiness: identifiers, hints, and formalization reports for pcs-core / Lean."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.release_run import file_content_digest
from labtrust_gym.pcs.workflow_profile import WorkflowProfileView, workflow_profile_view

PROOF_OBLIGATION_HINTS_NAME = "proof_obligation_hints.json"
PROOF_OBLIGATION_IDENTIFIERS_NAME = "proof_obligation_identifiers.json"
FORMALIZATION_READINESS_REPORT_NAME = "formalization_readiness_report.json"

DEFAULT_TRUST_KERNEL = "PCS.ReleaseChain"
DEFAULT_FORMALIZATION_SCOPE = "trust_envelope_only"
DEFAULT_REQUIRED_OBLIGATIONS: tuple[str, ...] = (
    "CertificateMatchesRuntime",
    "VerificationAdmitsBundle",
    "SignedBundleAdmissible",
)

HINT_ARTIFACT_PATHS: tuple[str, ...] = (
    "runtime_receipt.json",
    "trace_certificate.json",
    "science_claim_bundle.certified.json",
)

DOWNSTREAM_PF_ARTIFACTS: tuple[str, ...] = (
    "verification_result.json",
    "signed_science_claim_bundle.json",
)

LEAN_OBLIGATION_CERTIFICATE_MATCHES_RUNTIME = "CertificateMatchesRuntime"
LEAN_OBLIGATION_VERIFICATION_ADMITS = "VerificationAdmitsBundle"
LEAN_OBLIGATION_SIGNED_ADMISSIBLE = "SignedBundleAdmissible"


@dataclass(frozen=True)
class FormalizationPolicy:
    trust_kernel: str
    required_obligations: tuple[str, ...]
    formalization_scope: str

    @classmethod
    def from_profile(cls, profile: WorkflowProfileView) -> FormalizationPolicy:
        block = profile.document.get("formalization") or {}
        return cls(
            trust_kernel=str(block.get("trust_kernel", DEFAULT_TRUST_KERNEL)),
            required_obligations=tuple(
                block.get("required_obligations", DEFAULT_REQUIRED_OBLIGATIONS)
            ),
            formalization_scope=str(
                block.get("formalization_scope", DEFAULT_FORMALIZATION_SCOPE)
            ),
        )


def assert_formalization_block_valid(block: dict[str, Any]) -> None:
    """Validate LabTrust ``formalization`` extension on WorkflowProfile.v0."""
    if block.get("formalization_scope") != DEFAULT_FORMALIZATION_SCOPE:
        raise ValueError(
            "formalization.formalization_scope must be trust_envelope_only "
            "(LabTrust does not formalize hospital workflow semantics in Lean)"
        )
    obligations = block.get("required_obligations")
    if not isinstance(obligations, list) or not obligations:
        raise ValueError("formalization.required_obligations must be a non-empty list")
    for name in DEFAULT_REQUIRED_OBLIGATIONS:
        if name not in obligations:
            raise ValueError(f"formalization.required_obligations missing {name!r}")
    if not str(block.get("trust_kernel", "")).strip():
        raise ValueError("formalization.trust_kernel is required")


def pcs_workflow_profile_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Strip LabTrust-only extensions before pcs-core schema validation."""
    return {k: v for k, v in doc.items() if k != "formalization"}


def collect_proof_obligation_identifiers(release_dir: Path) -> dict[str, Any]:
    """Stable identifiers for ProofObligation.v0 extraction."""
    release_dir = release_dir.resolve()
    manifest_path = release_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = json.loads((release_dir / "runtime_receipt.json").read_text(encoding="utf-8"))
    certificate = json.loads((release_dir / "trace_certificate.json").read_text(encoding="utf-8"))
    certified = json.loads(
        (release_dir / "science_claim_bundle.certified.json").read_text(encoding="utf-8")
    )
    claim = certified["claim_artifact"]

    signed_path = release_dir / "signed_science_claim_bundle.json"
    signed_bundle_hash: str | None = None
    if signed_path.is_file():
        signed_bundle_hash = file_content_digest(signed_path)

    verification_path = release_dir / "verification_result.json"
    verified_input_bundle_hash: str | None = None
    if verification_path.is_file():
        vr = json.loads(verification_path.read_text(encoding="utf-8"))
        verified = vr.get("verified_input") or {}
        verified_input_bundle_hash = verified.get("bundle_hash")

    profile_path = release_dir / "workflow_profile.v0.json"
    workflow_id = manifest.get("workflow_id")
    if profile_path.is_file():
        profile_doc = json.loads(profile_path.read_text(encoding="utf-8"))
        workflow_id = profile_doc.get("workflow_id", workflow_id)

    return {
        "runtime_receipt_id": receipt.get("receipt_id"),
        "trace_hash": manifest.get("trace_hash") or receipt.get("trace_hash"),
        "certificate_id": manifest.get("certificate_id") or certificate.get("certificate_id"),
        "certificate_trace_hash": certificate.get("trace_hash"),
        "certified_bundle_hash": manifest.get("certified_bundle_hash")
        or file_content_digest(release_dir / "science_claim_bundle.certified.json"),
        "signed_bundle_hash": signed_bundle_hash,
        "verified_input_bundle_hash": verified_input_bundle_hash,
        "workflow_id": workflow_id,
        "property_id": certificate.get("property_id"),
        "claim_id": claim.get("artifact_id"),
        "source_commits": {
            "labtrust_gym_commit": manifest.get("labtrust_gym_commit"),
            "certifyedge_commit": manifest.get("certifyedge_commit"),
            "pcs_core_commit": manifest.get("pcs_core_commit"),
            "runtime_receipt_source_commit": receipt.get("source_commit"),
            "certificate_source_commit": certificate.get("source_commit"),
        },
    }


def build_proof_obligation_hints(
    release_dir: Path,
    *,
    profile: WorkflowProfileView | None = None,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    """Hints for pcs-core to locate formalizable artifacts without LabTrust internals."""
    release_dir = release_dir.resolve()
    profile = profile or workflow_profile_view(policy_root=policy_root)
    policy = FormalizationPolicy.from_profile(profile)
    ids = collect_proof_obligation_identifiers(release_dir)

    return {
        "workflow_id": profile.property_id,
        "claim_id": ids["claim_id"],
        "runtime_receipt": "runtime_receipt.json",
        "trace_certificate": "trace_certificate.json",
        "certified_bundle": "science_claim_bundle.certified.json",
        "required_obligations": list(policy.required_obligations),
    }


def build_formalization_readiness_report(
    release_dir: Path,
    *,
    profile: WorkflowProfileView | None = None,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    """Report whether LabTrust emitted enough structure for Lean obligation extraction."""
    release_dir = release_dir.resolve()
    profile = profile or workflow_profile_view(policy_root=policy_root)
    policy = FormalizationPolicy.from_profile(profile)

    missing: list[str] = []
    for name in HINT_ARTIFACT_PATHS:
        if not (release_dir / name).is_file():
            missing.append(name)

    for name in ("manifest.json", "trace.json", PROOF_OBLIGATION_IDENTIFIERS_NAME):
        if not (release_dir / name).is_file():
            missing.append(name)

    downstream_missing = [
        name for name in DOWNSTREAM_PF_ARTIFACTS if not (release_dir / name).is_file()
    ]

    labtrust_ready = not missing
    status = "passed" if labtrust_ready else "failed"

    return {
        "workflow_id": profile.workflow_id,
        "formalization_scope": policy.formalization_scope,
        "required_obligations": list(policy.required_obligations),
        "all_required_inputs_present": labtrust_ready,
        "missing_inputs": missing + downstream_missing,
        "status": status,
    }


def write_formalization_artifacts(
    release_dir: Path,
    *,
    profile: WorkflowProfileView | None = None,
    policy_root: Path | None = None,
) -> list[Path]:
    """Write hints, identifiers, and readiness report under ``release_dir``."""
    release_dir = release_dir.resolve()
    profile = profile or workflow_profile_view(policy_root=policy_root)

    identifiers = collect_proof_obligation_identifiers(release_dir)
    hints = build_proof_obligation_hints(release_dir, profile=profile)
    report = build_formalization_readiness_report(release_dir, profile=profile)

    written: list[Path] = []
    from labtrust_gym.pcs.bench_schemas import (
        validate_formalization_readiness_report,
        validate_proof_obligation_hints,
        validate_proof_obligation_identifiers,
    )

    payloads = (
        (PROOF_OBLIGATION_IDENTIFIERS_NAME, identifiers, validate_proof_obligation_identifiers),
        (PROOF_OBLIGATION_HINTS_NAME, hints, validate_proof_obligation_hints),
        (FORMALIZATION_READINESS_REPORT_NAME, report, validate_formalization_readiness_report),
    )
    for name, doc, validator in payloads:
        validator(doc)
        path = release_dir / name
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


def check_certificate_matches_runtime(artifacts_root: Path) -> None:
    """CertificateMatchesRuntime: receipt and certificate trace hashes align."""
    root = artifacts_root.resolve()
    receipt = json.loads((root / "runtime_receipt.json").read_text(encoding="utf-8"))
    cert = json.loads((root / "trace_certificate.json").read_text(encoding="utf-8"))
    receipt_hash = receipt.get("trace_hash")
    cert_hash = cert.get("trace_hash")
    if not receipt_hash or not cert_hash:
        raise ValueError("missing trace_hash on receipt or certificate")
    if receipt_hash != cert_hash:
        raise ValueError(
            f"CertificateMatchesRuntime failed: receipt {receipt_hash!r} != "
            f"certificate {cert_hash!r}"
        )


def check_certificate_status_allowed(artifacts_root: Path) -> None:
    """Lean extraction requires certificate status CertificateChecked (not Rejected/Stale)."""
    root = artifacts_root.resolve()
    cert = json.loads((root / "trace_certificate.json").read_text(encoding="utf-8"))
    status = cert.get("status")
    if status in ("Rejected", "Stale"):
        raise ValueError(f"certificate status {status!r} blocks Lean obligations")
    if status != "CertificateChecked":
        raise ValueError(f"unexpected certificate status {status!r}")


def check_verification_admits_bundle(artifacts_root: Path) -> None:
    """VerificationAdmitsBundle: verified_input.bundle_hash matches certified bundle."""
    root = artifacts_root.resolve()
    vr_path = root / "verification_result.json"
    if not vr_path.is_file():
        raise ValueError("missing verification_result.json for VerificationAdmitsBundle")
    certified_path = root / "science_claim_bundle.certified.json"
    if not certified_path.is_file():
        raise ValueError("missing science_claim_bundle.certified.json")
    vr = json.loads(vr_path.read_text(encoding="utf-8"))
    verified = vr.get("verified_input") or {}
    bundle_hash = verified.get("bundle_hash")
    if not bundle_hash:
        raise ValueError("verification_result.verified_input.bundle_hash missing")
    actual = file_content_digest(certified_path)
    if bundle_hash != actual:
        raise ValueError(
            f"VerificationAdmitsBundle failed: verified_input {bundle_hash!r} != "
            f"certified {actual!r}"
        )


def check_signed_bundle_admissible(artifacts_root: Path) -> None:
    """SignedBundleAdmissible: signed bundle digest matches verification verified_input."""
    root = artifacts_root.resolve()
    signed_path = root / "signed_science_claim_bundle.json"
    vr_path = root / "verification_result.json"
    if not signed_path.is_file():
        raise ValueError("missing signed_science_claim_bundle.json")
    if not vr_path.is_file():
        raise ValueError("missing verification_result.json")
    signed_hash = file_content_digest(signed_path)
    vr = json.loads(vr_path.read_text(encoding="utf-8"))
    verified = vr.get("verified_input") or {}
    input_hash = verified.get("bundle_hash")
    if not input_hash:
        raise ValueError("verification_result.verified_input.bundle_hash missing")
    if signed_hash != input_hash:
        raise ValueError(
            f"SignedBundleAdmissible failed: signed {signed_hash!r} != "
            f"verified_input {input_hash!r}"
        )


LEAN_OBLIGATION_CHECKS: dict[str, Any] = {
    LEAN_OBLIGATION_CERTIFICATE_MATCHES_RUNTIME: check_certificate_matches_runtime,
    LEAN_OBLIGATION_VERIFICATION_ADMITS: check_verification_admits_bundle,
    LEAN_OBLIGATION_SIGNED_ADMISSIBLE: check_signed_bundle_admissible,
}


def run_lean_obligation_check(obligation: str, artifacts_root: Path) -> None:
    """Run one named obligation check (raises on failure)."""
    if obligation == LEAN_OBLIGATION_CERTIFICATE_MATCHES_RUNTIME:
        check_certificate_matches_runtime(artifacts_root)
        check_certificate_status_allowed(artifacts_root)
        return
    fn = LEAN_OBLIGATION_CHECKS.get(obligation)
    if fn is None:
        raise ValueError(f"unknown Lean obligation {obligation!r}")
    check_certificate_status_allowed(artifacts_root)
    fn(artifacts_root)
