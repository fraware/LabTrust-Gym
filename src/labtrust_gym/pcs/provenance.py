"""Shared provenance fields for PCS artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.hash import pcs_digest
from labtrust_gym.version import __version__

SOURCE_REPO = "https://github.com/fraware/LabTrust-Gym"
PRODUCER = "labtrust-gym"


def normalize_timestamp(ts: str) -> str:
    """Normalize to Zulu ISO-8601 when possible."""
    if ts.endswith("+00:00"):
        return ts[:-6] + "Z"
    return ts


def source_commit(policy_root: Path | None = None) -> str:
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=policy_root or get_repo_root(),
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "0000000000000000000000000000000000000000"


def base_provenance(*, policy_root: Path | None = None) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "producer": PRODUCER,
        "producer_version": __version__,
        "source_repo": SOURCE_REPO,
        "source_commit": source_commit(policy_root),
    }


def with_signature(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out["signature_or_digest"] = pcs_digest(out)
    return out
