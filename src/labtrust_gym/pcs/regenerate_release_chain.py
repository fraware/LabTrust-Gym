"""Regenerate LabTrust PCS release chain from a fresh deterministic demo run."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_certificate_files
from labtrust_gym.pcs.demo import run_demo
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace
from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    build_runtime_to_certificate_handoff,
)
from labtrust_gym.pcs.manifest import resolve_pcs_core_root
from labtrust_gym.pcs.release_fragment import emit_labtrust_release_fragment
from labtrust_gym.pcs.release_run import (
    RELEASE_RUN_REL,
    promote_release_run_atomic,
    resolve_release_repo_commits,
    write_run_manifests,
)
from labtrust_gym.pcs.sync_pcs_core_rc import (
    compare_release_to_pcs_core_rc,
    pcs_core_labtrust_release_dir,
    verify_release_sync_gate,
)


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


def regenerate_release_chain(
    out_dir: Path,
    *,
    policy_root: Path | None = None,
    certifyedge_bin: str = "certifyedge",
    certifyedge_spec: Path | None = None,
    certifyedge_root: Path | None = None,
    pcs_core_dir: Path | None = None,
    run_dir: Path | None = None,
    generator: str = "regenerate_release_chain",
) -> Path:
    """
    Build LabTrust release fixtures from scratch: demo → export → CertifyEdge → attach → handoffs.

    When ``pcs_core_dir`` is set, verifies the promoted ``release/`` tree against canonical RC fixtures.
    """
    root = policy_root or get_repo_root()
    out_dir = out_dir.resolve()
    release_run = out_dir.parent / "release-run" if out_dir.name == "release" else out_dir / "_run"
    if release_run.resolve() == out_dir.resolve():
        release_run = out_dir.parent / "release-run"
    if release_run.exists():
        shutil.rmtree(release_run)
    release_run.mkdir(parents=True)

    ce_root = certifyedge_root or (root.parent / "CertifyEdge")
    spec = certifyedge_spec or (ce_root / "templates" / "hospital_lab" / "qc_release.stl")
    if not spec.is_file():
        raise FileNotFoundError(f"CertifyEdge spec not found: {spec}")

    ce_bin = _resolve_certifyedge_bin(certifyedge_bin, ce_root)
    ce_commit = subprocess.check_output(
        ["git", "-C", str(ce_root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    os.environ["CERTIFYEDGE_SOURCE_COMMIT"] = ce_commit
    os.environ.setdefault("PCS_DETERMINISTIC", "1")
    os.environ.setdefault("PCS_RELEASE_FIXTURE", "1")

    demo_run = run_dir or (root / "runs" / "qc-release-regenerate")
    if demo_run.exists():
        shutil.rmtree(demo_run)
    run_demo("qc-release", out_dir=demo_run, policy_root=root, deterministic=True)

    export_trace(demo_run, release_run / "trace.json")
    export_runtime_receipt(demo_run, release_run / "runtime_receipt.json", policy_root=root)
    export_pcs_bundle(demo_run, release_run / "science_claim_bundle.pending.json", policy_root=root)

    handoff_ce = build_runtime_to_certificate_handoff(
        release_run / "trace.json",
        receipt_path=release_run / "runtime_receipt.json",
        policy_root=root,
        release_mode=True,
    )
    (release_run / HANDOFF_TO_CERTIFYEDGE_NAME).write_text(
        json.dumps(handoff_ce, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    cert_path = release_run / "trace_certificate.json"
    from labtrust_gym.pcs.certifyedge_client import normalize_certifyedge_certificate_provenance

    subprocess.run(
        [
            ce_bin,
            "--release-mode",
            "emit-pcs-certificate",
            "--spec",
            str(spec),
            "--trace",
            str(release_run / "trace.json"),
            "--out",
            str(cert_path),
        ],
        check=True,
        env={**os.environ, "CERTIFYEDGE_SOURCE_COMMIT": ce_commit},
    )
    normalize_certifyedge_certificate_provenance(cert_path, source_commit=ce_commit)
    subprocess.run(["pcs", "validate", str(cert_path)], check=True, cwd=root)
    subprocess.run(
        [ce_bin, "verify-certificate", str(cert_path), "--trace", str(release_run / "trace.json")],
        check=True,
    )

    attach_certificate_files(
        release_run / "science_claim_bundle.pending.json",
        cert_path,
        release_run / "science_claim_bundle.certified.json",
    )
    subprocess.run(
        ["pcs", "validate", str(release_run / "science_claim_bundle.certified.json")],
        check=True,
        cwd=root,
    )

    commits = resolve_release_repo_commits(
        root,
        certifyedge_root=ce_root,
        pcs_core_root=pcs_core_dir or resolve_pcs_core_root(root),
    )
    os.environ["CERTIFYEDGE_ROOT"] = str(ce_root)
    os.environ["CERTIFYEDGE_BIN"] = ce_bin
    os.environ["CERTIFYEDGE_SPEC"] = str(spec)
    write_run_manifests(release_run, commits, generator=generator)

    promote_release_run_atomic(
        release_run,
        out_dir,
        generator=generator,
        certifyedge_bin=ce_bin,
        certifyedge_spec=str(spec),
    )
    emit_labtrust_release_fragment(release_dir=out_dir, source_commit=commits["labtrust_gym_commit"])

    if pcs_core_dir is not None:
        canonical = (
            pcs_core_dir
            if (pcs_core_dir / "trace.json").is_file()
            else pcs_core_labtrust_release_dir(root)
        )
        verify_release_sync_gate(out_dir, canonical)
    return out_dir


def compare_release_hashes_to_canonical(
    release_dir: Path,
    canonical_dir: Path,
) -> list[str]:
    """Return check labels when ``release_dir`` matches pcs-core canonical artifact hashes."""
    return compare_release_to_pcs_core_rc(release_dir.resolve(), canonical_dir.resolve())
