"""PCS failure gallery: protocolized negative fixtures for benchmarks and demos."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME
from labtrust_gym.pcs.manifest import PLACEHOLDER_COMMITS
from labtrust_gym.pcs.release_protocol import LEGACY_PF_HANDOFF_NAME
from labtrust_gym.pcs.release_protocol_producer import LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS
from labtrust_gym.pcs.status_policy import assert_failed_runtime_receipt, assert_release_bundle_status_policy
from labtrust_gym.pcs.status_transitions import mark_bundle_stale_if_trace_diverged
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol
from labtrust_gym.pcs.workflow_profile import WorkflowProfileView, workflow_profile_view
from labtrust_gym.pcs.workflows.registry import get_workflow_by_key

_PROTOCOL_ARTIFACTS = LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS


@dataclass(frozen=True)
class FailureCaseSpec:
    case_id: str
    description: str
    expected_failing_check: str
    expected_failure_code: str
    responsible_component: str
    repair_hint: str
    builder: Callable[[Path, Path, Path, WorkflowProfileView], list[str]]


def _artifacts_dir(case_dir: Path) -> Path:
    d = case_dir / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


from labtrust_gym.pcs.failure_case_manifest import (
    FAILURE_CASE_MANIFEST_NAME,
    FailureCaseManifest,
)


def _write_case_metadata(
    case_dir: Path,
    spec: FailureCaseSpec,
    *,
    workflow_id: str,
    artifact_names: list[str],
) -> None:
    (case_dir / "expected_failure.json").write_text(
        json.dumps(
            {
                "case_id": spec.case_id,
                "expected_failing_check": spec.expected_failing_check,
                "expected_failure_code": spec.expected_failure_code,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (case_dir / "repair_hint.json").write_text(
        json.dumps({"hint": spec.repair_hint}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    FailureCaseManifest(
        failure_case_id=spec.case_id,
        workflow_id=workflow_id,
        expected_failure_code=spec.expected_failure_code,
        responsible_component=spec.responsible_component,
        artifacts=tuple(artifact_names),
        repair_hint=spec.repair_hint,
    ).write(case_dir)
    readme = (
        f"# {spec.case_id}\n\n"
        f"{spec.description}\n\n"
        f"- Expected check: `{spec.expected_failing_check}`\n"
        f"- Expected code: `{spec.expected_failure_code}`\n"
        f"- Repair: see `repair_hint.json`\n"
    )
    (case_dir / "README.md").write_text(readme, encoding="utf-8")


def _copy_protocol_baseline(src: Path, artifacts: Path) -> list[str]:
    written: list[str] = []
    for name in _PROTOCOL_ARTIFACTS:
        path = src / name
        if path.is_file():
            shutil.copy2(path, artifacts / name)
            written.append(name)
    for extra in ("manifest.json", "trace_hash_alignment.json"):
        path = src / extra
        if path.is_file():
            shutil.copy2(path, artifacts / extra)
            written.append(extra)
    return written


def _build_runtime_failure(
    demo_case_id: str,
    *,
    expected_reason: str,
    policy_root: Path,
    _release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    from labtrust_gym.pcs.workflows.qc_release import run_failure_demo

    run_dir = run_failure_demo(
        demo_case_id,
        out_dir=artifacts / "_run",
        policy_root=policy_root,
        deterministic=True,
    )
    written: list[str] = []
    meta_path = run_dir / "run_meta.json"
    if meta_path.is_file():
        shutil.copy2(meta_path, artifacts / "run_meta.json")
        written.append("run_meta.json")
    trace_path = run_dir / "trace.json"
    if trace_path.is_file():
        shutil.copy2(trace_path, artifacts / "trace.json")
        written.append("trace.json")

    from labtrust_gym.pcs.export import export_runtime_receipt

    receipt_path = artifacts / "runtime_receipt.json"
    receipt = export_runtime_receipt(run_dir, receipt_path, policy_root=policy_root)
    assert_failed_runtime_receipt(receipt, expected_reason=expected_reason)
    written.append("runtime_receipt.json")
    return written


def _build_missing_qc(
    policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    profile: WorkflowProfileView,
) -> list[str]:
    return _build_runtime_failure(
        "qc-release-invalid-missing-qc",
        expected_reason="missing_qc",
        policy_root=policy_root,
        _release_dir=release_dir,
        artifacts=artifacts,
        _profile=profile,
    )


def _build_unauthorized(
    policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    profile: WorkflowProfileView,
) -> list[str]:
    return _build_runtime_failure(
        "qc-release-invalid-unauthorized",
        expected_reason="unauthorized_release",
        policy_root=policy_root,
        _release_dir=release_dir,
        artifacts=artifacts,
        _profile=profile,
    )


def _build_trace_hash_tamper(
    _policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    written = _copy_protocol_baseline(release_dir, artifacts)
    trace_path = artifacts / "trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace["trace_hash"] = "sha256:" + "f" * 64
    trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def _build_certificate_id_tamper(
    _policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    written = _copy_protocol_baseline(release_dir, artifacts)
    cert_path = artifacts / "trace_certificate.json"
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    cert["certificate_id"] = "cert-trace-tampered"
    cert_path.write_text(json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def _build_stale_trace_after_certificate(
    _policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    written = _copy_protocol_baseline(release_dir, artifacts)
    bundle_path = artifacts / "science_claim_bundle.certified.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["runtime_receipts"][0]["trace_hash"] = "sha256:" + "a" * 64
    try:
        mark_bundle_stale_if_trace_diverged(bundle, context="certified bundle")
    except ValueError:
        pass
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def _build_legacy_handoff_file(
    _policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    written = _copy_protocol_baseline(release_dir, artifacts)
    legacy = artifacts / LEGACY_PF_HANDOFF_NAME
    legacy.write_text(
        json.dumps({"legacy": True, "handoff_kind": "pf_handoff"}, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(LEGACY_PF_HANDOFF_NAME)
    return written


def _build_lean_trace_hash_mismatch(
    _policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    written = _copy_protocol_baseline(release_dir, artifacts)
    cert_path = artifacts / "trace_certificate.json"
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    cert["trace_hash"] = "sha256:" + "b" * 64
    cert_path.write_text(json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def _build_lean_rejected_certificate(
    _policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    written = _copy_protocol_baseline(release_dir, artifacts)
    cert_path = artifacts / "trace_certificate.json"
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    cert["status"] = "Rejected"
    cert_path.write_text(json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def _build_lean_stale_certificate(
    _policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    written = _copy_protocol_baseline(release_dir, artifacts)
    cert_path = artifacts / "trace_certificate.json"
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    cert["status"] = "Stale"
    cert_path.write_text(json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def _build_lean_signed_hash_mismatch(
    policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    from labtrust_gym.pcs.sync_pcs_core_rc import pcs_core_labtrust_release_dir

    written = _copy_protocol_baseline(release_dir, artifacts)
    try:
        canon = pcs_core_labtrust_release_dir(policy_root)
    except FileNotFoundError:
        canon = release_dir
    for name in ("verification_result.json", "signed_science_claim_bundle.json"):
        src = canon / name
        if src.is_file():
            shutil.copy2(src, artifacts / name)
            written.append(name)
    vr_path = artifacts / "verification_result.json"
    if vr_path.is_file():
        vr = json.loads(vr_path.read_text(encoding="utf-8"))
        verified = vr.setdefault("verified_input", {})
        verified["bundle_hash"] = "sha256:" + "c" * 64
        vr_path.write_text(json.dumps(vr, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    signed_path = artifacts / "signed_science_claim_bundle.json"
    if signed_path.is_file():
        signed = json.loads(signed_path.read_text(encoding="utf-8"))
        signed["signature_or_digest"] = "sha256:" + "d" * 64
        signed_path.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def _build_placeholder_commit(
    _policy_root: Path,
    release_dir: Path,
    artifacts: Path,
    _profile: WorkflowProfileView,
) -> list[str]:
    written = _copy_protocol_baseline(release_dir, artifacts)
    receipt_path = artifacts / "runtime_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    placeholder = next(iter(PLACEHOLDER_COMMITS))
    receipt["source_commit"] = placeholder
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def _failure_case_specs(profile: WorkflowProfileView) -> tuple[FailureCaseSpec, ...]:
    """Build case specs; ``profile.failure_modes`` must list every case id."""
    specs = (
        FailureCaseSpec(
            case_id="missing_qc_result",
            description="QC release workflow fails when required QC step is missing.",
            expected_failing_check="workflow.run_meta.released",
            expected_failure_code="missing_qc",
            responsible_component="workflow.runtime",
            repair_hint="Complete the QC verification step before release_sample.",
            builder=_build_missing_qc,
        ),
        FailureCaseSpec(
            case_id="unauthorized_release",
            description="Release rejected when actor lacks authorization.",
            expected_failing_check="workflow.run_meta.released",
            expected_failure_code="unauthorized_release",
            responsible_component="workflow.runtime",
            repair_hint="Use an authorized actor role for release_sample.",
            builder=_build_unauthorized,
        ),
        FailureCaseSpec(
            case_id="trace_hash_tamper",
            description="Handoff digest check fails when trace.json bytes disagree with declared trace_hash.",
            expected_failing_check="handoff_to_certifyedge_input_digests_fresh",
            expected_failure_code="STALE_HANDOFF_DIGEST",
            responsible_component="workflow.handoff",
            repair_hint="Regenerate trace.json from the workflow run; do not edit trace_hash in isolation.",
            builder=_build_trace_hash_tamper,
        ),
        FailureCaseSpec(
            case_id="certificate_id_tamper",
            description="Certificate id propagation fails after trace_certificate tampering.",
            expected_failing_check="certificate_id_propagation",
            expected_failure_code="CERTIFICATE_ID_MISMATCH",
            responsible_component="certifyedge.certificate",
            repair_hint="Re-run CertifyEdge emit-pcs-certificate and attach-certificate without editing certificate_id.",
            builder=_build_certificate_id_tamper,
        ),
        FailureCaseSpec(
            case_id="stale_trace_after_certificate",
            description="Certified bundle marked Stale when receipt trace_hash diverges from certificate.",
            expected_failing_check="certified_trace_hash_consistent",
            expected_failure_code="STALE_TRACE_AFTER_CERTIFICATE",
            responsible_component="workflow.status_policy",
            repair_hint="Re-attach certificate after any trace change, or regenerate the protocol package.",
            builder=_build_stale_trace_after_certificate,
        ),
        FailureCaseSpec(
            case_id="legacy_handoff_file",
            description="Release protocol rejects legacy pf_handoff.json at release root.",
            expected_failing_check="no_legacy_pf_handoff_root",
            expected_failure_code="LEGACY_HANDOFF_FILE",
            responsible_component="workflow.handoff",
            repair_hint="Remove pf_handoff.json; emit handoff_to_pf.json (HandoffManifest.v0).",
            builder=_build_legacy_handoff_file,
        ),
        FailureCaseSpec(
            case_id="placeholder_commit",
            description="Release evidence must not use placeholder source_commit values.",
            expected_failing_check="no_placeholder_commits",
            expected_failure_code="PLACEHOLDER_SOURCE_COMMIT",
            responsible_component="workflow.provenance",
            repair_hint="Regenerate artifacts with real git provenance (PCS_RELEASE_FIXTURE=1, no placeholder commits).",
            builder=_build_placeholder_commit,
        ),
        FailureCaseSpec(
            case_id="lean_trace_hash_mismatch",
            description="Lean CertificateMatchesRuntime fails when certificate trace_hash diverges from runtime receipt.",
            expected_failing_check="lean_obligation.CertificateMatchesRuntime",
            expected_failure_code="LEAN_CERTIFICATE_TRACE_HASH_MISMATCH",
            responsible_component="lean.extraction",
            repair_hint="Regenerate trace_certificate from the runtime receipt; do not desynchronize trace_hash fields.",
            builder=_build_lean_trace_hash_mismatch,
        ),
        FailureCaseSpec(
            case_id="lean_rejected_certificate",
            description="Lean obligations must fail when trace_certificate status is Rejected.",
            expected_failing_check="lean_obligation.CertificateMatchesRuntime",
            expected_failure_code="LEAN_CERTIFICATE_REJECTED",
            responsible_component="lean.extraction",
            repair_hint="Re-emit certificate with CertificateChecked status after a passing runtime.",
            builder=_build_lean_rejected_certificate,
        ),
        FailureCaseSpec(
            case_id="lean_stale_certificate",
            description="Lean obligations must fail when trace_certificate status is Stale.",
            expected_failing_check="lean_obligation.CertificateMatchesRuntime",
            expected_failure_code="LEAN_CERTIFICATE_STALE",
            responsible_component="lean.extraction",
            repair_hint="Re-attach certificate after trace mutation; mark Stale only after intentional divergence tests.",
            builder=_build_lean_stale_certificate,
        ),
        FailureCaseSpec(
            case_id="lean_signed_hash_mismatch",
            description="Lean VerificationAdmitsBundle / SignedBundleAdmissible fail on verified_input vs bundle hash mismatch.",
            expected_failing_check="lean_obligation.VerificationAdmitsBundle",
            expected_failure_code="LEAN_VERIFIED_INPUT_HASH_MISMATCH",
            responsible_component="lean.extraction",
            repair_hint="Align verification_result.verified_input.bundle_hash with science_claim_bundle.certified.json digest.",
            builder=_build_lean_signed_hash_mismatch,
        ),
    )
    spec_ids = {s.case_id for s in specs}
    profile_modes = set(profile.failure_modes)
    if spec_ids != profile_modes:
        raise ValueError(
            f"failure gallery cases {sorted(spec_ids)} != WorkflowProfile.failure_modes {sorted(profile_modes)}"
        )
    return specs


def build_single_failure_case(
    case_id: str,
    case_dir: Path,
    *,
    policy_root: Path,
    release_dir: Path,
    profile_path: Path | None = None,
) -> list[str]:
    """Build one failure-gallery case (README, metadata, ``artifacts/``)."""
    profile = workflow_profile_view(profile_path, policy_root=policy_root)
    spec = next((s for s in _failure_case_specs(profile) if s.case_id == case_id), None)
    if spec is None:
        raise ValueError(f"unknown failure gallery case {case_id!r}")
    case_dir = case_dir.resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    artifacts = _artifacts_dir(case_dir)
    written = spec.builder(policy_root, release_dir, artifacts, profile)
    _write_case_metadata(
        case_dir,
        spec,
        workflow_id=profile.workflow_id,
        artifact_names=written,
    )
    return written


def generate_failure_gallery(
    out_dir: Path,
    *,
    workflow_key: str,
    policy_root: Path,
    release_dir: Path | None = None,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    """
    Generate failure gallery cases under ``out_dir/<case_id>/``.

    Each case includes ``failure_case_manifest.json``, ``README.md``, ``artifacts/``,
    ``expected_failure.json``, and ``repair_hint.json``.
    """
    profile = workflow_profile_view(profile_path, policy_root=policy_root)
    workflow = get_workflow_by_key(workflow_key, policy_root=policy_root, profile_path=profile.path)
    release = release_dir or (policy_root / "examples" / "pcs_qc_release" / "release")
    if not (release / "trace.json").is_file():
        raise FileNotFoundError(f"release baseline not found: {release}")

    out_dir = out_dir.resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    cases_out: list[dict[str, Any]] = []
    for spec in _failure_case_specs(profile):
        case_dir = out_dir / spec.case_id
        case_dir.mkdir(parents=True)
        artifacts = _artifacts_dir(case_dir)
        input_artifacts = spec.builder(policy_root, release, artifacts, profile)
        _write_case_metadata(
            case_dir,
            spec,
            workflow_id=profile.workflow_id,
            artifact_names=input_artifacts,
        )
        rel_dir = case_dir.name
        try:
            rel_dir = str(case_dir.resolve().relative_to(out_dir.resolve()))
        except ValueError:
            rel_dir = str(case_dir)
        cases_out.append(
            {
                "case_id": spec.case_id,
                "directory": rel_dir.replace("\\", "/"),
                "input_artifacts": input_artifacts,
                "expected_failing_check": spec.expected_failing_check,
                "expected_failure_code": spec.expected_failure_code,
            }
        )

    try:
        profile_rel = str(profile.path.resolve().relative_to(policy_root.resolve())).replace("\\", "/")
    except ValueError:
        profile_rel = str(profile.path)

    index = {
        "status": "passed",
        "workflow_id": profile.workflow_id,
        "property_id": profile.property_id,
        "workflow_profile": profile_rel,
        "cases": cases_out,
        "out_dir": "failures",
    }
    (out_dir / "gallery_index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index


def _case_artifacts_root(case_dir: Path) -> Path:
    """Release-shaped tree for protocol checks (``artifacts/`` subfolder)."""
    artifacts = case_dir / "artifacts"
    if not artifacts.is_dir():
        raise FileNotFoundError(f"missing artifacts/ in {case_dir}")
    return artifacts


def demonstrate_case_failure(case_dir: Path, *, policy_root: Path | None = None) -> str:
    """Run the check that should fail; returns the expected failing check label."""
    case_dir = case_dir.resolve()
    expected = json.loads((case_dir / "expected_failure.json").read_text(encoding="utf-8"))
    case_id = expected["case_id"]
    check = expected["expected_failing_check"]
    root = _case_artifacts_root(case_dir)

    if case_id in ("missing_qc_result", "unauthorized_release"):
        meta = json.loads((root / "run_meta.json").read_text(encoding="utf-8"))
        if meta.get("released") is True:
            raise AssertionError(f"{case_id}: expected failed run")
        return check

    if case_id == "legacy_handoff_file":
        from labtrust_gym.pcs.release_protocol import assert_no_legacy_pf_handoff

        try:
            assert_no_legacy_pf_handoff(root)
        except ValueError:
            return check
        raise AssertionError("legacy handoff was not rejected")

    if case_id == "trace_hash_tamper":
        try:
            verify_release_protocol(root, policy_root=policy_root)
        except ValueError as exc:
            if "digest" in str(exc).lower() or "stale" in str(exc).lower():
                return check
            raise
        raise AssertionError("trace tamper did not fail verification")

    if case_id == "stale_trace_after_certificate":
        try:
            assert_release_bundle_status_policy(root)
        except ValueError as exc:
            if "stale" in str(exc).lower() or "diverged" in str(exc).lower():
                return check
            raise
        raise AssertionError("stale trace case did not fail status policy")

    if case_id == "certificate_id_tamper":
        from labtrust_gym.pcs.release_handoff import verify_release_handoff

        try:
            verify_release_handoff(root)
        except ValueError as exc:
            if "certificate_id" in str(exc).lower():
                return check
            raise
        raise AssertionError("certificate id tamper did not fail handoff verify")

    if case_id == "placeholder_commit":
        from labtrust_gym.pcs.sync_pcs_core_rc import assert_release_not_using_placeholder_commits

        try:
            assert_release_not_using_placeholder_commits(root)
        except ValueError:
            return check
        raise AssertionError("placeholder commit was not rejected")

    if case_id.startswith("lean_"):
        from labtrust_gym.pcs.formalization import (
            LEAN_OBLIGATION_CERTIFICATE_MATCHES_RUNTIME,
            LEAN_OBLIGATION_SIGNED_ADMISSIBLE,
            LEAN_OBLIGATION_VERIFICATION_ADMITS,
            run_lean_obligation_check,
        )

        obligation_by_case = {
            "lean_trace_hash_mismatch": LEAN_OBLIGATION_CERTIFICATE_MATCHES_RUNTIME,
            "lean_rejected_certificate": LEAN_OBLIGATION_CERTIFICATE_MATCHES_RUNTIME,
            "lean_stale_certificate": LEAN_OBLIGATION_CERTIFICATE_MATCHES_RUNTIME,
            "lean_signed_hash_mismatch": LEAN_OBLIGATION_VERIFICATION_ADMITS,
        }
        obligation = obligation_by_case[case_id]
        try:
            run_lean_obligation_check(obligation, root)
            if case_id == "lean_signed_hash_mismatch":
                run_lean_obligation_check(LEAN_OBLIGATION_SIGNED_ADMISSIBLE, root)
        except ValueError:
            return check
        raise AssertionError(f"{case_id}: expected Lean obligation failure")

    raise ValueError(f"unknown gallery case {case_id!r}")


def verify_failure_gallery(gallery_root: Path, *, policy_root: Path | None = None) -> list[str]:
    """Assert every case fails its documented check."""
    gallery_root = gallery_root.resolve()
    index_path = gallery_root / "gallery_index.json"
    if not index_path.is_file():
        raise FileNotFoundError(f"missing gallery index: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    checks: list[str] = []
    for entry in index.get("cases", []):
        case_id = entry["case_id"]
        case_dir = gallery_root / case_id
        if not case_dir.is_dir():
            raise FileNotFoundError(f"missing gallery case directory: {case_dir}")
        label = demonstrate_case_failure(case_dir, policy_root=policy_root)
        expected = json.loads((case_dir / "expected_failure.json").read_text(encoding="utf-8"))[
            "expected_failing_check"
        ]
        if label != expected:
            raise ValueError(f"{case_id}: got {label!r}, expected {expected!r}")
        for name in (
            "README.md",
            "expected_failure.json",
            "repair_hint.json",
            FAILURE_CASE_MANIFEST_NAME,
        ):
            if not (case_dir / name).is_file():
                raise FileNotFoundError(f"{case_id} missing {name}")
        manifest = json.loads((case_dir / FAILURE_CASE_MANIFEST_NAME).read_text(encoding="utf-8"))
        if manifest.get("failure_case_id") != case_id:
            raise ValueError(f"{case_id}: manifest failure_case_id mismatch")
        if manifest.get("workflow_id") != index.get("workflow_id"):
            raise ValueError(f"{case_id}: manifest workflow_id mismatch")
        checks.append(f"gallery_case.{case_id}")
    profile_path = index.get("workflow_profile")
    if profile_path:
        from labtrust_gym.pcs.workflow_profile import assert_workflow_profile_valid, load_workflow_profile

        p = Path(profile_path)
        if not p.is_file():
            if policy_root is not None:
                p = policy_root / profile_path
            elif not p.is_absolute():
                p = gallery_root.parent / p
        doc = load_workflow_profile(p)
        assert_workflow_profile_valid(doc)
        checks.append("workflow_profile_valid")
    return checks
