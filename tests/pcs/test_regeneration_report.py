"""regeneration_report.json shape and builders."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.protocol_artifacts import ProtocolRegenerationResult
from labtrust_gym.pcs.regeneration_report import (
    REGENERATION_REPORT_NAME,
    build_regeneration_report,
    failed_regeneration_report,
    write_regeneration_report,
)

_REQUIRED_KEYS = frozenset(
    {
        "workflow_id",
        "artifacts_written",
        "artifact_hashes",
        "handoffs_written",
        "certificate_id",
        "trace_hash",
        "certified_bundle_hash",
        "duration_ms",
        "status",
        "failure_code",
    }
)


def test_build_regeneration_report_from_release(release_dir: Path) -> None:
    result = ProtocolRegenerationResult(release_dir=release_dir, run_dir=release_dir)
    report = build_regeneration_report(
        result,
        workflow_id="labtrust.qc_release_v0.1",
        duration_ms=42,
    )
    data = report.to_dict()
    assert _REQUIRED_KEYS <= set(data)
    assert data["status"] == "passed"
    assert data["failure_code"] is None
    assert data["duration_ms"] == 42
    assert "trace.json" in data["artifacts_written"]
    assert data["trace_hash"]
    assert data["certificate_id"]


def test_failed_regeneration_report(tmp_path: Path) -> None:
    report = failed_regeneration_report(
        workflow_id="example.workflow",
        duration_ms=10,
        failure_code="FileNotFoundError",
    )
    assert report.status == "failed"
    assert report.failure_code == "FileNotFoundError"
    path = write_regeneration_report(tmp_path / REGENERATION_REPORT_NAME, report)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert _REQUIRED_KEYS <= set(doc)
