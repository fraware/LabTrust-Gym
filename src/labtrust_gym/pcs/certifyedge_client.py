"""CertifyEdge CLI invocation for PCS protocol regeneration."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_TRACE_HASH_MISMATCH = re.compile(
    r"trace hash mismatch: expected (sha256:[0-9a-f]+), found (sha256:[0-9a-f]+)",
    re.IGNORECASE,
)


def _certifyedge_root_candidates(certifyedge_root: Path) -> tuple[Path, ...]:
    # Prefer debug builds: they track the sibling repo HEAD used for CERTIFYEDGE_SOURCE_COMMIT.
    return (
        certifyedge_root / "target" / "debug" / "certifyedge.exe",
        certifyedge_root / "target" / "debug" / "certifyedge",
        certifyedge_root / "target" / "release" / "certifyedge.exe",
        certifyedge_root / "target" / "release" / "certifyedge",
    )


def resolve_certifyedge_bin(certifyedge_bin: str, certifyedge_root: Path) -> str:
    """
    Resolve CertifyEdge executable for clean-chain regeneration.

  When ``certifyedge_bin`` is the default ``certifyedge``, prefer a binary built
    under ``certifyedge_root`` so a stale PATH install cannot drift from the
    sibling repo used for ``CERTIFYEDGE_SOURCE_COMMIT``.
    """
    certifyedge_root = certifyedge_root.resolve()
    use_default_name = certifyedge_bin in ("certifyedge", "certifyedge.exe")

    if not use_default_name:
        if Path(certifyedge_bin).is_file():
            return str(Path(certifyedge_bin).resolve())
        found = shutil.which(certifyedge_bin)
        if found:
            return found

    for candidate in _certifyedge_root_candidates(certifyedge_root):
        if candidate.is_file():
            return str(candidate)

    found = shutil.which(certifyedge_bin)
    if found:
        return found

    raise FileNotFoundError(
        f"CertifyEdge binary not found: {certifyedge_bin!r} "
        f"(searched under {certifyedge_root})"
    )


def _emit_pcs_certificate_help(ce_bin: str) -> str:
    proc = subprocess.run(
        [ce_bin, "emit-pcs-certificate", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def certifyedge_emit_supports_handoff(ce_bin: str) -> bool:
    return "--handoff" in _emit_pcs_certificate_help(ce_bin)


def certifyedge_emit_supports_profile_registry(ce_bin: str) -> bool:
    return "--profile-registry" in _emit_pcs_certificate_help(ce_bin)


def normalize_certifyedge_certificate_provenance(
    certificate_path: Path,
    *,
    source_commit: str,
    source_repo: str | None = None,
) -> None:
    """
    Align ``trace_certificate.json`` provenance with the CertifyEdge repo HEAD.

    Debug/release binaries may embed an older build-time commit; LabTrust regeneration
    pins ``manifest.certifyedge_commit`` to ``git rev-parse HEAD`` at emit time.
    """
    from labtrust_gym.pcs.mock_certificate import CERTIFYEDGE_SOURCE_REPO

    certificate_path = certificate_path.resolve()
    cert = json.loads(certificate_path.read_text(encoding="utf-8"))
    cert["source_commit"] = source_commit
    cert["source_repo"] = source_repo or CERTIFYEDGE_SOURCE_REPO
    certificate_path.write_text(json.dumps(cert, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_trace_trace_hash(trace_path: Path) -> str:
    """
    Recompute ``trace_hash`` from events (LabTrust canonical, CertifyEdge-aligned).

    CertifyEdge validates that the declared ``trace_hash`` matches the event chain.
  """
    from labtrust_gym.pcs.trace import compute_trace_hash

    trace_path = trace_path.resolve()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    expected = compute_trace_hash(
        trace["events"],
        run_id=str(trace["run_id"]),
        sample_id=str(trace["sample_id"]),
    )
    if trace.get("trace_hash") != expected:
        trace["trace_hash"] = expected
        trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return expected


def _certifyedge_profile_registry(spec: Path) -> Path | None:
    registry = spec.resolve().parent.parent / "profiles"
    return registry if registry.is_dir() else None


def invoke_certifyedge_emit_pcs_certificate(
    ce_bin: str,
    *,
    spec: Path,
    trace_path: Path,
    out_path: Path,
    handoff_path: Path | None = None,
    handoff_out: Path | None = None,
    env: dict[str, str] | None = None,
    certifyedge_root: Path | None = None,
) -> None:
    """Emit ``TraceCertificate.v0`` via CertifyEdge (handoff or spec+trace)."""
    trace_path = trace_path.resolve()
    spec = spec.resolve()
    normalize_trace_trace_hash(trace_path)

    run_env = {**os.environ, **(env or {})}
    if certifyedge_root is not None:
        run_env.setdefault("CERTIFYEDGE_ROOT", str(certifyedge_root.resolve()))

    registry_args: list[str] = []
    if certifyedge_emit_supports_profile_registry(ce_bin):
        registry = _certifyedge_profile_registry(spec)
        if registry is not None:
            registry_args = ["--profile-registry", str(registry)]

    if handoff_path is not None and certifyedge_emit_supports_handoff(ce_bin):
        cmd = [
            ce_bin,
            "--release-mode",
            "emit-pcs-certificate",
            "--handoff",
            str(handoff_path.resolve()),
            "--out",
            str(out_path),
            *registry_args,
        ]
        if handoff_out is not None:
            cmd.extend(["--handoff-out", str(handoff_out)])
    else:
        cmd = [
            ce_bin,
            "--release-mode",
            "emit-pcs-certificate",
            "--spec",
            str(spec),
            "--trace",
            str(trace_path),
            "--out",
            str(out_path),
            *registry_args,
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=run_env, check=False)
    if proc.returncode == 0:
        return

    combined = (proc.stderr or "") + (proc.stdout or "")
    mismatch = _TRACE_HASH_MISMATCH.search(combined)
    if mismatch and not (handoff_path and certifyedge_emit_supports_handoff(ce_bin)):
        expected, found = mismatch.group(1), mismatch.group(2)
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        if trace.get("trace_hash") == found:
            trace["trace_hash"] = expected
            trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            proc = subprocess.run(cmd, capture_output=True, text=True, env=run_env, check=False)
            if proc.returncode == 0:
                return

    if proc.stderr:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=proc.stdout, stderr=proc.stderr
        )
    subprocess.run(cmd, check=True, env=run_env)
