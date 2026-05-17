"""Release fixture manifest with real git provenance (no placeholder commits)."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import DETERMINISTIC_CERT_SOURCE_COMMIT, DETERMINISTIC_SOURCE_COMMIT
from labtrust_gym.pcs.mock_certificate import CERTIFYEDGE_SOURCE_REPO

PLACEHOLDER_COMMITS = frozenset(
    {
        DETERMINISTIC_SOURCE_COMMIT,
        DETERMINISTIC_CERT_SOURCE_COMMIT,
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "local-dev",
    }
)


def _git_head(cwd: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=cwd,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    raise RuntimeError(f"git HEAD unavailable for {cwd}")


def resolve_pcs_core_root(labtrust_root: Path | None = None) -> Path:
    import os

    raw = os.environ.get("PCS_CORE_PATH", "").strip()
    if raw:
        p = Path(raw)
        return p.parent if p.name == "python" else p
    parent = (labtrust_root or get_repo_root()).parent / "pcs-core"
    if parent.is_dir():
        return parent
    raise FileNotFoundError("pcs-core not found; set PCS_CORE_PATH")


def build_release_manifest(
    release_dir: Path,
    *,
    generator: str,
    certifyedge_bin: str,
    certifyedge_spec: str,
    certifyedge_root: Path | None = None,
    labtrust_root: Path | None = None,
    pcs_core_root: Path | None = None,
) -> dict[str, Any]:
    """Write manifest.json with real commit SHAs for LabTrust, CertifyEdge, and pcs-core."""
    lt = labtrust_root or get_repo_root()
    ce = certifyedge_root or (lt.parent / "CertifyEdge")
    pc = pcs_core_root or resolve_pcs_core_root(lt)

    labtrust_commit = _git_head(lt)
    certifyedge_commit = _git_head(ce)
    pcs_core_commit = _git_head(pc)

    for label, commit in (
        ("labtrust_gym_commit", labtrust_commit),
        ("certifyedge_commit", certifyedge_commit),
        ("pcs_core_commit", pcs_core_commit),
    ):
        if commit in PLACEHOLDER_COMMITS or len(commit) < 12:
            raise ValueError(f"{label} must be a real git SHA, got {commit!r}")

    cert_path = release_dir / "trace_certificate.json"
    cert = json.loads(cert_path.read_text(encoding="utf-8"))

    spec_path = Path(certifyedge_spec)
    if spec_path.is_absolute():
        try:
            certifyedge_spec_recorded = spec_path.relative_to(lt.parent).as_posix()
        except ValueError:
            certifyedge_spec_recorded = spec_path.as_posix()
    else:
        certifyedge_spec_recorded = spec_path.as_posix()

    manifest: dict[str, Any] = {
        "schema_version": "v0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": generator,
        "mock_certificate": False,
        "labtrust_gym_commit": labtrust_commit,
        "certifyedge_commit": certifyedge_commit,
        "pcs_core_commit": pcs_core_commit,
        "certifyedge_bin": certifyedge_bin,
        "certifyedge_spec": certifyedge_spec_recorded,
        "certificate_id": cert.get("certificate_id"),
        "certificate_source_repo": cert.get("source_repo"),
        "certificate_producer": cert.get("producer"),
    }
    path = release_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def validate_release_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("mock_certificate") is not False:
        raise ValueError("manifest.mock_certificate must be false")
    for key in ("labtrust_gym_commit", "certifyedge_commit", "pcs_core_commit"):
        commit = manifest.get(key)
        if not commit or commit in PLACEHOLDER_COMMITS:
            raise ValueError(f"manifest.{key} must be a real git commit, got {commit!r}")
    repo = manifest.get("certificate_source_repo")
    if repo != CERTIFYEDGE_SOURCE_REPO:
        raise ValueError(f"manifest certificate_source_repo must be {CERTIFYEDGE_SOURCE_REPO}")
    for key in ("handoff_id", "certificate_id", "trace_hash", "certified_bundle_hash"):
        if not manifest.get(key):
            raise ValueError(f"manifest.{key} is required for pcs-core handoff")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or len(artifacts) < 5:
        raise ValueError("manifest.artifacts must list all handoff artifact digests")
