"""
LabTrust PCS Phase 2 protocol package producer.

Single orchestration surface for the LabTrust-owned artifacts in the
``runtime_to_certificate`` → CertifyEdge → ``bundle_to_verifier`` trust loop.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_certificate_files
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    emit_handoff_to_certifyedge,
    emit_handoff_to_pf,
)
from labtrust_gym.pcs.manifest import resolve_pcs_core_root
from labtrust_gym.pcs.release_fragment import (
    LABTRUST_RELEASE_FRAGMENT_NAME,
    emit_labtrust_release_fragment,
)
from labtrust_gym.pcs.release_run import (
    promote_release_run_atomic,
    resolve_release_repo_commits,
    write_run_manifests,
)
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol

# LabTrust-side protocol package (Provability Fabric / Scientific Memory are downstream).
LABTRUST_PROTOCOL_CORE_ARTIFACTS: tuple[str, ...] = (
    "trace.json",
    "runtime_receipt.json",
    "science_claim_bundle.pending.json",
    "trace_certificate.json",
    "science_claim_bundle.certified.json",
)

LABTRUST_PROTOCOL_HANDOFF_ARTIFACTS: tuple[str, ...] = (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    LABTRUST_RELEASE_FRAGMENT_NAME,
)

LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS: tuple[str, ...] = (
    *LABTRUST_PROTOCOL_CORE_ARTIFACTS,
    *LABTRUST_PROTOCOL_HANDOFF_ARTIFACTS,
)


@dataclass(frozen=True)
class ProtocolRegenerationResult:
    """Outcome of ``regenerate_release_protocol``."""

    release_dir: Path
    run_dir: Path
    checks: list[str] = field(default_factory=list)
    commits: dict[str, str] = field(default_factory=dict)


def assert_protocol_package_complete(release_dir: Path) -> None:
    """Raise when any required LabTrust protocol artifact is missing under ``release_dir``."""
    release_dir = release_dir.resolve()
    missing = [name for name in LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS if not (release_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"incomplete LabTrust protocol package; missing: {', '.join(missing)}")


def _resolve_certifyedge_bin(certifyedge_bin: str, certifyedge_root: Path) -> str:
    if shutil.which(certifyedge_bin):
        return certifyedge_bin
    for candidate in (
        certifyedge_root / "target" / "debug" / "certifyedge",
        certifyedge_root / "target" / "debug" / "certifyedge.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"CertifyEdge binary not found: {certifyedge_bin!r}")


def regenerate_release_protocol(
    out_dir: Path,
    *,
    policy_root: Path | None = None,
    certifyedge_bin: str = "certifyedge",
    certifyedge_spec: Path | None = None,
    certifyedge_root: Path | None = None,
    pcs_core: Path | None = None,
    run_dir: Path | None = None,
    property_id: str = "hospital_lab.qc_release",
) -> ProtocolRegenerationResult:
    """
    Generate the complete LabTrust PCS protocol package from a clean deterministic demo run.

    Writes all ``LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS`` under ``out_dir``, promotes handoff
    metadata, and runs ``verify_release_protocol``.
    """
    root = policy_root or get_repo_root()
    out_dir = out_dir.resolve()
    work = out_dir.parent / ".protocol-regen-staging"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    ce_root = certifyedge_root or (root.parent / "CertifyEdge")
    spec = certifyedge_spec or (ce_root / "templates" / "hospital_lab" / "qc_release.stl")
    if not spec.is_file():
        raise FileNotFoundError(f"CertifyEdge spec not found: {spec}")

    ce_bin = _resolve_certifyedge_bin(certifyedge_bin, ce_root)
    ce_commit = subprocess.check_output(
        ["git", "-C", str(ce_root), "rev-parse", "HEAD"],
        text=True,
    ).strip()

    os.environ.setdefault("PCS_DETERMINISTIC", "1")
    os.environ.setdefault("PCS_RELEASE_FIXTURE", "1")
    os.environ["CERTIFYEDGE_SOURCE_COMMIT"] = ce_commit

    demo_run = run_dir or (root / "runs" / "qc-release-protocol-regen")
    if demo_run.exists():
        shutil.rmtree(demo_run)
    run_demo("qc-release", out_dir=demo_run, policy_root=root, deterministic=True)

    export_trace(demo_run, work / "trace.json")
    export_runtime_receipt(demo_run, work / "runtime_receipt.json", policy_root=root)
    export_pcs_bundle(demo_run, work / "science_claim_bundle.pending.json", policy_root=root)

    emit_handoff_to_certifyedge(
        trace_path=work / "trace.json",
        runtime_receipt_path=work / "runtime_receipt.json",
        out_path=work / HANDOFF_TO_CERTIFYEDGE_NAME,
        policy_root=root,
        property_id=property_id,
        release_mode=True,
    )

    cert_path = work / "trace_certificate.json"
    subprocess.run(
        [
            ce_bin,
            "--release-mode",
            "emit-pcs-certificate",
            "--spec",
            str(spec),
            "--trace",
            str(work / "trace.json"),
            "--out",
            str(cert_path),
        ],
        check=True,
        env={**os.environ, "CERTIFYEDGE_SOURCE_COMMIT": ce_commit},
    )
    subprocess.run(["pcs", "validate", str(cert_path)], check=True, cwd=root)
    subprocess.run(
        [ce_bin, "verify-certificate", str(cert_path), "--trace", str(work / "trace.json")],
        check=True,
    )

    attach_certificate_files(
        work / "science_claim_bundle.pending.json",
        cert_path,
        work / "science_claim_bundle.certified.json",
    )
    subprocess.run(
        ["pcs", "validate", str(work / "science_claim_bundle.certified.json")],
        check=True,
        cwd=root,
    )

    emit_handoff_to_pf(
        bundle_path=work / "science_claim_bundle.certified.json",
        out_path=work / HANDOFF_TO_PF_NAME,
        policy_root=root,
        release_mode=True,
    )

    if pcs_core is not None and (pcs_core / "trace.json").is_file():
        pcs_git_root = resolve_pcs_core_root(root)
    elif pcs_core is not None:
        pcs_git_root = pcs_core.resolve()
    else:
        pcs_git_root = resolve_pcs_core_root(root)
    commits = resolve_release_repo_commits(
        root,
        certifyedge_root=ce_root,
        pcs_core_root=pcs_git_root,
    )
    write_run_manifests(work, commits, generator="regenerate_release_protocol")

    os.environ["CERTIFYEDGE_ROOT"] = str(ce_root)
    os.environ["CERTIFYEDGE_BIN"] = ce_bin
    os.environ["CERTIFYEDGE_SPEC"] = str(spec)

    promote_release_run_atomic(
        work,
        out_dir,
        generator="regenerate_release_protocol",
        certifyedge_bin=ce_bin,
        certifyedge_spec=str(spec),
    )
    emit_labtrust_release_fragment(
        release_dir=out_dir,
        policy_root=root,
        source_commit=commits["labtrust_gym_commit"],
    )

    assert_protocol_package_complete(out_dir)
    checks = verify_release_protocol(out_dir, pcs_core=pcs_core, policy_root=root)

    if work.exists():
        shutil.rmtree(work, ignore_errors=True)

    return ProtocolRegenerationResult(
        release_dir=out_dir,
        run_dir=demo_run,
        checks=checks,
        commits=commits,
    )


def emit_protocol_package_from_release(
    release_dir: Path,
    *,
    policy_root: Path | None = None,
    property_id: str = "hospital_lab.qc_release",
) -> dict[str, Any]:
    """
    Re-emit handoffs and fragment from an existing release tree (no CertifyEdge re-run).

    Returns summary dict with paths and digests.
    """
    release_dir = release_dir.resolve()
    emit_handoff_to_certifyedge(
        trace_path=release_dir / "trace.json",
        runtime_receipt_path=release_dir / "runtime_receipt.json",
        out_path=release_dir / HANDOFF_TO_CERTIFYEDGE_NAME,
        policy_root=policy_root,
        property_id=property_id,
        release_mode=True,
    )
    emit_handoff_to_pf(
        bundle_path=release_dir / "science_claim_bundle.certified.json",
        out_path=release_dir / HANDOFF_TO_PF_NAME,
        policy_root=policy_root,
        release_mode=True,
    )
    fragment = emit_labtrust_release_fragment(release_dir=release_dir, policy_root=policy_root)
    checks = verify_release_protocol(release_dir, policy_root=policy_root)
    return {
        "release_dir": str(release_dir),
        "checks": checks,
        "fragment_digest": fragment.get("signature_or_digest"),
    }
