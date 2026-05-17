"""Shared provenance fields for PCS artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import DETERMINISTIC_SOURCE_COMMIT, use_frozen_provenance
from labtrust_gym.pcs.hash import pcs_digest
from labtrust_gym.pcs.schema_version import SCHEMA_VERSION
from labtrust_gym.version import __version__

SOURCE_REPO = "https://github.com/fraware/LabTrust-Gym"
PRODUCER = "labtrust-gym"
LOCAL_DEV_COMMIT = "local-dev"


def normalize_timestamp(ts: str) -> str:
    """Normalize to Zulu ISO-8601 when possible."""
    if ts.endswith("+00:00"):
        return ts[:-6] + "Z"
    return ts


def _read_git_head(cwd: Path) -> str | None:
    """Return git HEAD for *cwd*, or None when git is unavailable."""
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return None


def resolve_source_commit(policy_root: Path | None = None) -> tuple[str, bool]:
    """
    Return (source_commit, local_dev).

    When git HEAD is unavailable, use explicit local-dev marker and local_dev=True
    instead of a silent placeholder hash.
    """
    if use_frozen_provenance():
        return DETERMINISTIC_SOURCE_COMMIT, False
    head = _read_git_head(policy_root or get_repo_root())
    if head:
        return head, False
    return LOCAL_DEV_COMMIT, True


def base_provenance(*, policy_root: Path | None = None) -> dict[str, Any]:
    commit, local_dev = resolve_source_commit(policy_root)
    fields: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER,
        "producer_version": __version__,
        "source_repo": SOURCE_REPO,
        "source_commit": commit,
    }
    if local_dev:
        fields["local_dev"] = True
    return fields


def with_signature(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out["signature_or_digest"] = pcs_digest(out)
    return out
