"""Register PCS v0.1 CLI subcommands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from labtrust_gym.cli.console import get_console
from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_certificate_files
from labtrust_gym.pcs.demo import run_demo as execute_pcs_demo
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = get_repo_root() / p
    return p


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
        f"status={meta['status']} released={meta['released']} reason={meta['final_reason_code']}"
    )
    return 0 if meta["status"] == "completed" else 0


def _run_export_trace(args: argparse.Namespace) -> int:
    run_dir = _resolve_path(args.run)
    out = _resolve_path(args.out)
    if not run_dir.is_dir():
        get_console().error(f"run directory not found: {run_dir}")
        return 1
    export_trace(run_dir, out)
    get_console().info(f"trace exported to {out}")
    return 0


def _run_export_runtime_receipt(args: argparse.Namespace) -> int:
    run_dir = _resolve_path(args.run)
    out = _resolve_path(args.out)
    if not run_dir.is_dir():
        get_console().error(f"run directory not found: {run_dir}")
        return 1
    export_runtime_receipt(run_dir, out)
    get_console().info(f"runtime receipt exported to {out}")
    return 0


def _run_export_pcs(args: argparse.Namespace) -> int:
    run_dir = _resolve_path(args.run)
    out = _resolve_path(args.out)
    if not run_dir.is_dir():
        get_console().error(f"run directory not found: {run_dir}")
        return 1
    export_pcs_bundle(run_dir, out)
    get_console().info(f"ScienceClaimBundle (pending) exported to {out}")
    return 0


def _run_attach_certificate(args: argparse.Namespace) -> int:
    bundle_path = _resolve_path(args.bundle)
    cert_path = _resolve_path(args.certificate)
    out_path = _resolve_path(args.out)
    try:
        attach_certificate_files(bundle_path, cert_path, out_path)
    except (FileNotFoundError, ValueError) as e:
        get_console().error(str(e))
        return 1
    get_console().info(f"certified bundle written to {out_path}")
    return 0


def register_pcs_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_demo = sub.add_parser(
        "run-demo",
        help="Run PCS QC-release demonstration workflow (valid or invalid scenarios)",
    )
    p_demo.add_argument(
        "demo",
        choices=[
            "qc-release",
            "qc-release-invalid-missing-qc",
            "qc-release-invalid-unauthorized",
        ],
        help="Demo scenario name",
    )
    p_demo.add_argument(
        "--out",
        default=None,
        help="Output run directory (default: runs/<scenario>)",
    )
    p_demo.set_defaults(func=_run_demo)

    p_trace = sub.add_parser("export-trace", help="Export PCS trace.json from a demo run")
    p_trace.add_argument("--run", required=True, help="Run directory (e.g. runs/qc-release)")
    p_trace.add_argument("--out", required=True, help="Output trace.json path")
    p_trace.set_defaults(func=_run_export_trace)

    p_receipt = sub.add_parser(
        "export-runtime-receipt",
        help="Export RuntimeReceipt.v0 from a demo run",
    )
    p_receipt.add_argument("--run", required=True, help="Run directory")
    p_receipt.add_argument("--out", required=True, help="Output runtime_receipt.json path")
    p_receipt.set_defaults(func=_run_export_runtime_receipt)

    p_pcs = sub.add_parser(
        "export-pcs",
        help="Export pending ScienceClaimBundle.v0 from a demo run",
    )
    p_pcs.add_argument("--run", required=True, help="Run directory")
    p_pcs.add_argument("--out", required=True, help="Output science_claim_bundle.pending.json path")
    p_pcs.set_defaults(func=_run_export_pcs)

    p_attach = sub.add_parser(
        "attach-certificate",
        help="Attach CertifyEdge TraceCertificate.v0 to a pending ScienceClaimBundle",
    )
    p_attach.add_argument("--bundle", required=True, help="Pending science claim bundle JSON")
    p_attach.add_argument("--certificate", required=True, help="trace_certificate.json from CertifyEdge")
    p_attach.add_argument("--out", required=True, help="Output certified bundle path")
    p_attach.set_defaults(func=_run_attach_certificate)
