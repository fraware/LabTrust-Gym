"""Register PCS v0.1 CLI subcommands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from labtrust_gym.cli.console import get_console
from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_certificate_files
from labtrust_gym.pcs.demo import DEMO_SCENARIOS
from labtrust_gym.pcs.demo import run_demo as execute_pcs_demo
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.handoff import export_handoff_bundle
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
        run_dir = execute_pcs_demo(name, out_dir=out)
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
