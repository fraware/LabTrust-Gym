"""Machine-readable summaries for PCS protocol regeneration (legacy alias)."""

from __future__ import annotations

from typing import Any

from labtrust_gym.pcs.protocol_artifacts import ProtocolRegenerationResult
from labtrust_gym.pcs.regeneration_report import build_regeneration_report


def build_protocol_regeneration_summary(
    result: ProtocolRegenerationResult,
    *,
    workflow_id: str,
    property_id: str,
    duration_ms: int = 0,
) -> dict[str, Any]:
    """Build JSON summary after a successful ``regenerate_release_protocol`` run."""
    report = build_regeneration_report(
        result,
        workflow_id=workflow_id,
        duration_ms=duration_ms,
    )
    summary = report.to_dict()
    summary["property_id"] = property_id
    summary["checks"] = result.checks
    summary["release_dir"] = str(result.release_dir)
    summary["commits"] = result.commits
    return summary
