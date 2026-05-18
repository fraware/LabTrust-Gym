"""Register PCS v0.1 CLI subcommands."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from labtrust_gym.cli.console import get_console
from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_certificate_files
from labtrust_gym.pcs.demo import DEMO_SCENARIOS
from labtrust_gym.pcs.demo import run_demo as execute_pcs_demo
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.handoff import export_handoff_bundle
from labtrust_gym.pcs.handoff_manifest import (
    emit_handoff_manifest,
    emit_handoff_to_certifyedge,
    emit_handoff_to_pf,
)
from labtrust_gym.pcs.failure_gallery import generate_failure_gallery
from labtrust_gym.pcs.regenerate_release_chain import regenerate_release_chain
from labtrust_gym.pcs.regenerate_release_protocol import regenerate_release_protocol
from labtrust_gym.pcs.release_protocol_producer import LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS
from labtrust_gym.pcs.release_fragment import emit_labtrust_release_fragment
from labtrust_gym.pcs.status_policy import check_release_status_policy
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol
from labtrust_gym.pcs.validate import PcsValidationError, validate_artifact_file, validate_run_dir


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = get_repo_root() / p
    return p


def _print_validation_errors(errors: list[str]) -> None:
    console = get_console()
    for err in errors:
        console.error(err)


def _run_demo(args: argparse.Namespace) -> int:
    name = args.demo
    out = _resolve_path(args.out) if args.out else None
    try:
        run_dir = execute_pcs_demo(name, out_dir=out, deterministic=args.deterministic)
    except ValueError as e:
        get_console().error(str(e))
        return 1
    get_console().info(f"PCS demo {name!r} written to {run_dir}")
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    get_console().info(
        f"status={meta['status']} released={meta['released']} "
        f"outcome={'passed' if meta.get('released') else 'failed'} "
        f"reason={meta['final_reason_code']}"
    )
    if args.validate:
        try:
            validate_run_dir(run_dir)
            get_console().info("run directory passed PCS integrity validation")
        except PcsValidationError as e:
            _print_validation_errors(e.errors)
            return 1
    if args.strict and not meta.get("released"):
        return 1
    return 0


def _run_export_trace(args: argparse.Namespace) -> int:
    run_dir = _resolve_path(args.run)
    out = _resolve_path(args.out)
    if not run_dir.is_dir():
        get_console().error(f"run directory not found: {run_dir}")
        return 1
    try:
        export_trace(run_dir, out, validate=not args.no_validate)
    except (PcsValidationError, FileNotFoundError) as e:
        if isinstance(e, PcsValidationError):
            _print_validation_errors(e.errors)
        else:
            get_console().error(str(e))
        return 1
    get_console().info(f"trace exported to {out}")
    return 0


def _run_export_runtime_receipt(args: argparse.Namespace) -> int:
    run_dir = _resolve_path(args.run)
    out = _resolve_path(args.out)
    if not run_dir.is_dir():
        get_console().error(f"run directory not found: {run_dir}")
        return 1
    try:
        export_runtime_receipt(run_dir, out, validate=not args.no_validate)
    except (PcsValidationError, FileNotFoundError) as e:
        if isinstance(e, PcsValidationError):
            _print_validation_errors(e.errors)
        else:
            get_console().error(str(e))
        return 1
    get_console().info(f"runtime receipt exported to {out}")
    return 0


def _run_export_pcs(args: argparse.Namespace) -> int:
    run_dir = _resolve_path(args.run)
    out = _resolve_path(args.out)
    if not run_dir.is_dir():
        get_console().error(f"run directory not found: {run_dir}")
        return 1
    try:
        export_pcs_bundle(run_dir, out, validate=not args.no_validate)
    except (PcsValidationError, FileNotFoundError) as e:
        if isinstance(e, PcsValidationError):
            _print_validation_errors(e.errors)
        else:
            get_console().error(str(e))
        return 1
    get_console().info(f"ScienceClaimBundle (pending) exported to {out}")
    return 0


def _run_attach_certificate(args: argparse.Namespace) -> int:
    bundle_path = _resolve_path(args.bundle)
    cert_path = _resolve_path(args.certificate)
    out_path = _resolve_path(args.out)
    try:
        certified = attach_certificate_files(bundle_path, cert_path, out_path)
        if not args.no_validate:
            from labtrust_gym.pcs.validate import validate_science_claim_bundle

            validate_science_claim_bundle(certified)
    except (FileNotFoundError, ValueError, PcsValidationError) as e:
        if isinstance(e, PcsValidationError):
            _print_validation_errors(e.errors)
        else:
            get_console().error(str(e))
        return 1
    get_console().info(f"certified bundle written to {out_path}")
    return 0


def _run_validate_pcs(args: argparse.Namespace) -> int:
    try:
        if args.run:
            validate_run_dir(_resolve_path(args.run))
            get_console().info(f"PCS run OK: {args.run}")
        elif args.artifact:
            kind = validate_artifact_file(_resolve_path(args.artifact))
            get_console().info(f"PCS artifact OK ({kind}): {args.artifact}")
        else:
            get_console().error("specify --run or --artifact")
            return 1
    except PcsValidationError as e:
        _print_validation_errors(e.errors)
        return 1
    except RuntimeError as e:
        get_console().error(str(e))
        return 1
    return 0


def _run_emit_release_fragment(args: argparse.Namespace) -> int:
    release_dir = _resolve_path(args.release_dir)
    out = _resolve_path(args.out) if args.out else release_dir / "labtrust_release_fragment.json"
    try:
        emit_labtrust_release_fragment(release_dir=release_dir, out_path=out)
    except (ValueError, FileNotFoundError) as e:
        get_console().error(str(e))
        return 1
    get_console().info(f"LabTrust release fragment written to {out}")
    return 0


def _run_emit_handoff(args: argparse.Namespace) -> int:
    out = _resolve_path(args.out)
    try:
        emit_handoff_manifest(
            kind=args.kind,
            out_path=out,
            bundle_path=_resolve_path(args.bundle) if args.bundle else None,
            trace_path=_resolve_path(args.trace) if args.trace else None,
            receipt_path=_resolve_path(args.receipt) if args.receipt else None,
            release_mode=args.release_mode,
            property_id=args.property_id,
        )
    except (ValueError, FileNotFoundError) as e:
        get_console().error(str(e))
        return 1
    get_console().info(f"HandoffManifest.v0 written to {out}")
    return 0


def _run_verify_release_protocol(args: argparse.Namespace) -> int:
    release_dir = _resolve_path(args.release_dir)
    pcs_core = _resolve_path(args.pcs_core) if args.pcs_core else None
    try:
        checks = verify_release_protocol(release_dir, pcs_core=pcs_core)
    except (ValueError, FileNotFoundError) as e:
        get_console().error(str(e))
        return 1
    for label in checks:
        get_console().info(f"OK {label}")
    get_console().info(f"release protocol verified: {release_dir}")
    return 0


def _run_verify_release_fixtures(args: argparse.Namespace) -> int:
    return _run_verify_release_protocol(args)


def _run_emit_handoff_to_certifyedge(args: argparse.Namespace) -> int:
    out = _resolve_path(args.out)
    try:
        emit_handoff_to_certifyedge(
            trace_path=_resolve_path(args.trace),
            runtime_receipt_path=_resolve_path(args.runtime_receipt),
            out_path=out,
            property_id=args.property_id,
            release_mode=args.release_mode,
        )
    except (ValueError, FileNotFoundError) as e:
        get_console().error(str(e))
        return 1
    get_console().info(f"handoff_to_certifyedge written to {out}")
    return 0


def _run_emit_handoff_to_pf(args: argparse.Namespace) -> int:
    out = _resolve_path(args.out)
    try:
        emit_handoff_to_pf(
            bundle_path=_resolve_path(args.bundle),
            out_path=out,
            release_mode=args.release_mode,
        )
    except (ValueError, FileNotFoundError) as e:
        get_console().error(str(e))
        return 1
    get_console().info(f"handoff_to_pf written to {out}")
    return 0


def _run_regenerate_release_protocol(args: argparse.Namespace) -> int:
    out = _resolve_path(args.out)
    pcs_core = _resolve_path(args.pcs_core) if args.pcs_core else None
    ce_spec = _resolve_path(args.certifyedge_spec) if args.certifyedge_spec else None
    ce_root = _resolve_path(args.certifyedge_root) if args.certifyedge_root else None
    profile_path = _resolve_path(args.workflow_profile) if getattr(args, "workflow_profile", None) else None
    try:
        release_dir, checks, summary = regenerate_release_protocol(
            out,
            certifyedge_bin=args.certifyedge_bin,
            certifyedge_spec=ce_spec,
            certifyedge_root=ce_root,
            pcs_core=pcs_core,
            workflow_profile=profile_path,
        )
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as e:
        get_console().error(f"labtrust regenerate-release-protocol failed: {e}")
        return 1
    if pcs_core is not None:
        try:
            rc_checks = verify_release_protocol(release_dir, pcs_core=pcs_core)
            checks = [*checks, *rc_checks]
        except (ValueError, FileNotFoundError) as e:
            get_console().error(f"labtrust verify-release-protocol (pcs-core RC) failed: {e}")
            return 1
    if getattr(args, "summary_out", None):
        summary_path = _resolve_path(args.summary_out)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json_summary:
        json.dump(summary, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    if not args.json_summary and not getattr(args, "summary_out", None):
        for name in LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS:
            if (release_dir / name).is_file():
                get_console().info(f"OK artifact {name}")
        for label in checks:
            get_console().info(f"OK {label}")
        report_file = release_dir / "regeneration_report.json"
        if report_file.is_file():
            get_console().info(f"OK regeneration report {report_file.name}")
        get_console().info(f"release protocol regenerated at {release_dir}")
    return 0


def _run_check_status_policy(args: argparse.Namespace) -> int:
    release_dir = _resolve_path(args.release_dir)
    try:
        profile_path = _resolve_path(args.workflow_profile) if getattr(args, "workflow_profile", None) else None
        result = check_release_status_policy(release_dir, profile_path=profile_path)
    except (ValueError, FileNotFoundError) as e:
        get_console().error(str(e))
        return 1
    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        for label in result.get("checks", []):
            get_console().info(f"OK {label}")
        get_console().info(f"status policy passed: {release_dir}")
    return 0


def _run_generate_failure_gallery(args: argparse.Namespace) -> int:
    out = _resolve_path(args.out)
    release_dir = _resolve_path(args.release_dir) if args.release_dir else None
    try:
        profile_path = _resolve_path(args.workflow_profile) if getattr(args, "workflow_profile", None) else None
        index = generate_failure_gallery(
            out,
            workflow_key=args.workflow,
            policy_root=get_repo_root(),
            release_dir=release_dir,
            profile_path=profile_path,
        )
    except (ValueError, FileNotFoundError) as e:
        get_console().error(str(e))
        return 1
    if args.json:
        json.dump(index, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        get_console().info(f"failure gallery written to {out} ({len(index['cases'])} cases)")
    return 0


def _run_regenerate_release_chain(args: argparse.Namespace) -> int:
    out = _resolve_path(args.out)
    pcs_core = _resolve_path(args.pcs_core) if args.pcs_core else None
    ce_spec = _resolve_path(args.certifyedge_spec) if args.certifyedge_spec else None
    ce_root = _resolve_path(args.certifyedge_root) if args.certifyedge_root else None
    try:
        regenerate_release_chain(
            out,
            certifyedge_bin=args.certifyedge_bin,
            certifyedge_spec=ce_spec,
            certifyedge_root=ce_root,
            pcs_core_dir=pcs_core,
        )
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as e:
        get_console().error(str(e))
        return 1
    get_console().info(f"release chain regenerated at {out}")
    return 0


def _run_export_handoff(args: argparse.Namespace) -> int:
    out = _resolve_path(args.out)
    try:
        manifest = export_handoff_bundle(
            out,
            validate=not args.no_validate,
            work_dir=_resolve_path(args.work_dir) if args.work_dir else None,
        )
    except (PcsValidationError, ValueError, RuntimeError) as e:
        if isinstance(e, PcsValidationError):
            _print_validation_errors(e.errors)
        else:
            get_console().error(str(e))
        return 1
    get_console().info(f"handoff bundle written to {out}")
    if args.json_manifest:
        json.dump(manifest, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


def _add_no_validate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip pcs-core validation on export (not recommended)",
    )


def register_pcs_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_demo = sub.add_parser(
        "run-demo",
        help="Run PCS QC-release demonstration workflow (valid or invalid scenarios)",
    )
    p_demo.add_argument(
        "demo",
        choices=list(DEMO_SCENARIOS.keys()),
        help="Demo scenario name",
    )
    p_demo.add_argument("--out", default=None, help="Output run directory")
    p_demo.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Validate run directory after execution (default: on)",
    )
    p_demo.add_argument(
        "--no-validate",
        action="store_false",
        dest="validate",
        help="Skip post-run validation",
    )
    p_demo.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 unless release_sample succeeded (released=true)",
    )
    p_demo.add_argument(
        "--deterministic",
        action="store_true",
        help="Fixture mode: freeze provenance and environment for golden artifacts (or set PCS_DETERMINISTIC=1)",
    )
    p_demo.set_defaults(func=_run_demo)

    p_trace = sub.add_parser("export-trace", help="Export PCS trace.json from a demo run")
    p_trace.add_argument("--run", required=True, help="Run directory")
    p_trace.add_argument("--out", required=True, help="Output trace.json path")
    _add_no_validate(p_trace)
    p_trace.set_defaults(func=_run_export_trace)

    p_receipt = sub.add_parser(
        "export-runtime-receipt",
        help="Export RuntimeReceipt.v0 from a demo run",
    )
    p_receipt.add_argument("--run", required=True, help="Run directory")
    p_receipt.add_argument("--out", required=True, help="Output runtime_receipt.json path")
    _add_no_validate(p_receipt)
    p_receipt.set_defaults(func=_run_export_runtime_receipt)

    p_pcs = sub.add_parser(
        "export-pcs",
        help="Export pending ScienceClaimBundle.v0 from a demo run",
    )
    p_pcs.add_argument("--run", required=True, help="Run directory")
    p_pcs.add_argument("--out", required=True, help="Output science_claim_bundle.pending.json")
    _add_no_validate(p_pcs)
    p_pcs.set_defaults(func=_run_export_pcs)

    p_attach = sub.add_parser(
        "attach-certificate",
        help="Attach CertifyEdge TraceCertificate.v0 to a pending ScienceClaimBundle",
    )
    p_attach.add_argument("--bundle", required=True, help="Pending science claim bundle JSON")
    p_attach.add_argument("--certificate", required=True, help="trace_certificate.json")
    p_attach.add_argument("--out", required=True, help="Output certified bundle path")
    _add_no_validate(p_attach)
    p_attach.set_defaults(func=_run_attach_certificate)

    p_validate = sub.add_parser(
        "validate-pcs",
        help="Validate PCS run directory or a single artifact JSON file (requires pcs-core)",
    )
    p_validate.add_argument("--run", default=None, help="Run directory with trace.json and pcs/")
    p_validate.add_argument("--artifact", default=None, help="Single PCS artifact JSON file")
    p_validate.set_defaults(func=_run_validate_pcs)

    p_emit = sub.add_parser(
        "emit-handoff",
        help="Emit HandoffManifest.v0 for Provability Fabric (bundle_to_verifier)",
    )
    p_emit.add_argument(
        "--kind",
        required=True,
        help="Handoff kind: bundle-to-verifier | runtime-to-certificate",
    )
    p_emit.add_argument(
        "--bundle",
        default=None,
        help="Certified science_claim_bundle.certified.json (bundle-to-verifier)",
    )
    p_emit.add_argument(
        "--trace",
        default=None,
        help="trace.json path (runtime-to-certificate)",
    )
    p_emit.add_argument(
        "--receipt",
        default=None,
        help="Optional runtime_receipt.json (runtime-to-certificate)",
    )
    p_emit.add_argument(
        "--property-id",
        default="hospital_lab.qc_release",
        help="property_id invariant for runtime-to-certificate",
    )
    p_emit.add_argument("--out", required=True, help="Output HandoffManifest.v0 path")
    p_emit.add_argument(
        "--release-mode",
        action="store_true",
        help="Reject local-dev provenance (default when inputs are under release/)",
    )
    p_emit.set_defaults(func=_run_emit_handoff)

    p_emit_ce = sub.add_parser(
        "emit-handoff-to-certifyedge",
        help="Emit HandoffManifest.v0 for CertifyEdge (runtime_to_certificate)",
    )
    p_emit_ce.add_argument("--trace", required=True, help="trace.json path")
    p_emit_ce.add_argument("--runtime-receipt", required=True, help="runtime_receipt.json path")
    p_emit_ce.add_argument(
        "--property-id",
        default="hospital_lab.qc_release",
        help="property_id invariant",
    )
    p_emit_ce.add_argument("--out", required=True, help="Output handoff_to_certifyedge.json path")
    p_emit_ce.add_argument(
        "--release-mode",
        action="store_true",
        help="Reject local-dev provenance",
    )
    p_emit_ce.set_defaults(func=_run_emit_handoff_to_certifyedge)

    p_emit_pf = sub.add_parser(
        "emit-handoff-to-pf",
        help="Emit HandoffManifest.v0 for Provability Fabric (bundle_to_verifier)",
    )
    p_emit_pf.add_argument(
        "--bundle",
        required=True,
        help="Certified science_claim_bundle.certified.json",
    )
    p_emit_pf.add_argument("--out", required=True, help="Output handoff_to_pf.json path")
    p_emit_pf.add_argument(
        "--release-mode",
        action="store_true",
        help="Reject local-dev provenance",
    )
    p_emit_pf.set_defaults(func=_run_emit_handoff_to_pf)

    p_verify_protocol = sub.add_parser(
        "verify-release-protocol",
        help="Verify Phase 2 protocol artifacts, digests, and optional pcs-core RC alignment",
    )
    p_verify_protocol.add_argument(
        "--release-dir",
        required=True,
        help="Release directory (e.g. examples/pcs_qc_release/release)",
    )
    p_verify_protocol.add_argument(
        "--pcs-core",
        default=None,
        help="pcs-core root or examples/labtrust-release for RC compare",
    )
    p_verify_protocol.set_defaults(func=_run_verify_release_protocol)

    p_verify_release = sub.add_parser(
        "verify-release-fixtures",
        help="Alias for verify-release-protocol",
    )
    p_verify_release.add_argument(
        "--release-dir",
        required=True,
        help="Release directory (e.g. examples/pcs_qc_release/release)",
    )
    p_verify_release.add_argument(
        "--pcs-core",
        default=None,
        help="pcs-core canonical labtrust-release directory for hash compare",
    )
    p_verify_release.set_defaults(func=_run_verify_release_fixtures)

    p_regen_protocol = sub.add_parser(
        "regenerate-release-protocol",
        help="Regenerate complete LabTrust-side PCS protocol package from scratch",
    )
    p_regen_protocol.add_argument(
        "--out",
        required=True,
        help="Output release directory",
    )
    p_regen_protocol.add_argument(
        "--certifyedge-bin",
        default="certifyedge",
        help="CertifyEdge CLI binary",
    )
    p_regen_protocol.add_argument(
        "--certifyedge-spec",
        default=None,
        help="CertifyEdge STL spec path",
    )
    p_regen_protocol.add_argument(
        "--certifyedge-root",
        default=None,
        help="CertifyEdge repo root (default: ../CertifyEdge)",
    )
    p_regen_protocol.add_argument(
        "--pcs-core",
        default=None,
        help="pcs-core root or examples/labtrust-release for validation",
    )
    p_regen_protocol.add_argument(
        "--json-summary",
        action="store_true",
        help="Print machine-readable JSON summary to stdout",
    )
    p_regen_protocol.add_argument(
        "--summary-out",
        default=None,
        help="Write machine-readable JSON summary to this path",
    )
    p_regen_protocol.add_argument(
        "--workflow-profile",
        default=None,
        help="WorkflowProfile.v0 path (default: examples/pcs_qc_release/workflow_profile.v0.json)",
    )
    p_regen_protocol.set_defaults(func=_run_regenerate_release_protocol)

    p_status = sub.add_parser(
        "check-status-policy",
        help="Enforce LabTrust status boundaries on release bundles (no ProofChecked)",
    )
    p_status.add_argument(
        "--release-dir",
        required=True,
        help="Release directory (e.g. examples/pcs_qc_release/release)",
    )
    p_status.add_argument(
        "--json",
        action="store_true",
        help="Print JSON result to stdout",
    )
    p_status.add_argument(
        "--workflow-profile",
        default=None,
        help="WorkflowProfile.v0 path (default: examples/pcs_qc_release/workflow_profile.v0.json)",
    )
    p_status.set_defaults(func=_run_check_status_policy)

    p_gallery = sub.add_parser(
        "generate-failure-gallery",
        help="Generate negative protocol fixtures for demos and benchmarks",
    )
    p_gallery.add_argument(
        "--workflow",
        default="hospital_lab.qc_release",
        help="Workflow id or property id (default: hospital_lab.qc_release)",
    )
    p_gallery.add_argument(
        "--out",
        required=True,
        help="Output directory (e.g. examples/pcs_qc_release/failures)",
    )
    p_gallery.add_argument(
        "--release-dir",
        default=None,
        help="Baseline release directory for tamper cases (default: examples/pcs_qc_release/release)",
    )
    p_gallery.add_argument(
        "--json",
        action="store_true",
        help="Print gallery index JSON to stdout",
    )
    p_gallery.add_argument(
        "--workflow-profile",
        default=None,
        help="WorkflowProfile.v0 path (default: examples/pcs_qc_release/workflow_profile.v0.json)",
    )
    p_gallery.set_defaults(func=_run_generate_failure_gallery)

    p_regen = sub.add_parser(
        "regenerate-release-chain",
        help="Alias for regenerate-release-protocol",
    )
    p_regen.add_argument(
        "--out",
        required=True,
        help="Output release directory",
    )
    p_regen.add_argument(
        "--certifyedge-bin",
        default="certifyedge",
        help="CertifyEdge CLI binary",
    )
    p_regen.add_argument(
        "--certifyedge-spec",
        default=None,
        help="CertifyEdge STL spec path",
    )
    p_regen.add_argument(
        "--certifyedge-root",
        default=None,
        help="CertifyEdge repo root (default: ../CertifyEdge)",
    )
    p_regen.add_argument(
        "--pcs-core",
        default=None,
        help="pcs-core root or examples/labtrust-release for post-regenerate verify",
    )
    p_regen.set_defaults(func=_run_regenerate_release_chain)

    p_fragment = sub.add_parser(
        "emit-release-fragment",
        help="Emit LabTrust-owned ReleaseManifest fragment for pcs-core aggregation",
    )
    p_fragment.add_argument(
        "--release-dir",
        required=True,
        help="Release directory (e.g. examples/pcs_qc_release/release)",
    )
    p_fragment.add_argument(
        "--out",
        default=None,
        help="Output path (default: <release-dir>/labtrust_release_fragment.json)",
    )
    p_fragment.set_defaults(func=_run_emit_release_fragment)

    p_handoff = sub.add_parser(
        "export-pcs-handoff",
        help="Export CertifyEdge + Provability Fabric handoff artifact bundle",
    )
    p_handoff.add_argument("--out", required=True, help="Output handoff directory")
    p_handoff.add_argument(
        "--work-dir",
        default=None,
        help="Keep intermediate run dirs (default: use <out>/_work then remove)",
    )
    p_handoff.add_argument("--json-manifest", action="store_true", help="Print manifest.json to stdout")
    _add_no_validate(p_handoff)
    p_handoff.set_defaults(func=_run_export_handoff)
