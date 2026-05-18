"""Machine-readable summaries for PCS protocol regeneration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.release_protocol_producer import (
    LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS,
    ProtocolRegenerationResult,
)
from labtrust_gym.pcs.release_run import file_content_digest


def build_protocol_regeneration_summary(
    result: ProtocolRegenerationResult,
    *,
    workflow_id: str,
    property_id: str,
) -> dict[str, Any]:
    """Build JSON summary after a successful ``regenerate_release_protocol`` run."""
    release_dir = result.release_dir.resolve()
    trace = json.loads((release_dir / "trace.json").read_text(encoding="utf-8"))
    cert = json.loads((release_dir / "trace_certificate.json").read_text(encoding="utf-8"))
    certified_path = release_dir / "science_claim_bundle.certified.json"

    artifacts_written = [name for name in LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS if (release_dir / name).is_file()]

    return {
        "status": "passed",
        "workflow_id": workflow_id,
        "property_id": property_id,
        "trace_hash": trace.get("trace_hash"),
        "certificate_id": cert.get("certificate_id"),
        "certified_bundle_hash": file_content_digest(certified_path),
        "artifacts_written": artifacts_written,
        "checks": result.checks,
        "release_dir": str(release_dir),
        "commits": result.commits,
    }
