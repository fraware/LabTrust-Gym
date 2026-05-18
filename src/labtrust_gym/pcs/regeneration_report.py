"""Machine-readable regeneration report for pcs-bench and CI drift checks."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
)
from labtrust_gym.pcs.protocol_artifacts import (
    LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS,
    ProtocolRegenerationResult,
)
from labtrust_gym.pcs.release_run import file_content_digest

REGENERATION_REPORT_NAME = "regeneration_report.json"

REQUIRED_REPORT_KEYS = frozenset(
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


@dataclass
class RegenerationReport:
    workflow_id: str
    artifacts_written: list[str] = field(default_factory=list)
    artifact_hashes: dict[str, str] = field(default_factory=dict)
    handoffs_written: list[str] = field(default_factory=list)
    certificate_id: str | None = None
    trace_hash: str | None = None
    certified_bundle_hash: str | None = None
    duration_ms: int = 0
    status: str = "passed"
    failure_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "artifacts_written": self.artifacts_written,
            "artifact_hashes": self.artifact_hashes,
            "handoffs_written": self.handoffs_written,
            "certificate_id": self.certificate_id,
            "trace_hash": self.trace_hash,
            "certified_bundle_hash": self.certified_bundle_hash,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "failure_code": self.failure_code,
        }


def assert_regeneration_report_valid(
    doc: dict[str, Any],
    *,
    release_dir: Path | None = None,
    expect_status: str = "passed",
    policy_root: Path | None = None,
) -> None:
    """Raise when ``doc`` is not a valid regeneration report (optional on-disk checks)."""
    from labtrust_gym.pcs.bench_schemas import validate_regeneration_report_doc

    validate_regeneration_report_doc(doc, policy_root=policy_root)
    missing = REQUIRED_REPORT_KEYS - set(doc)
    if missing:
        raise ValueError(f"regeneration report missing keys: {sorted(missing)}")
    if doc["status"] != expect_status:
        raise ValueError(f"expected status {expect_status!r}, got {doc['status']!r}")
    if expect_status == "passed" and doc.get("failure_code") is not None:
        raise ValueError(f"expected failure_code null on success, got {doc['failure_code']!r}")

    if release_dir is None:
        return

    release_dir = release_dir.resolve()
    trace_path = release_dir / "trace.json"
    if trace_path.is_file() and doc.get("trace_hash"):
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        if doc["trace_hash"] != trace.get("trace_hash"):
            raise ValueError("trace_hash mismatch vs trace.json")

    certified = release_dir / "science_claim_bundle.certified.json"
    if certified.is_file() and doc.get("certified_bundle_hash"):
        digest = file_content_digest(certified)
        if doc["certified_bundle_hash"] != digest:
            raise ValueError("certified_bundle_hash mismatch vs certified bundle")

    for name, digest in doc.get("artifact_hashes", {}).items():
        path = release_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"artifact_hashes lists missing file: {name}")
        if file_content_digest(path) != digest:
            raise ValueError(f"artifact_hashes[{name!r}] stale vs on-disk bytes")


def write_regeneration_report(path: Path, report: RegenerationReport) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = report.to_dict()
    from labtrust_gym.pcs.bench_schemas import validate_regeneration_report_doc

    validate_regeneration_report_doc(doc)
    payload = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    path.write_text(payload, encoding="utf-8")
    return path


def build_regeneration_report(
    result: ProtocolRegenerationResult,
    *,
    workflow_id: str,
    duration_ms: int,
    status: str = "passed",
    failure_code: str | None = None,
) -> RegenerationReport:
    """Build a report from a successful protocol regeneration."""
    release_dir = result.release_dir.resolve()
    artifacts_written = [
        name
        for name in LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS
        if (release_dir / name).is_file()
    ]
    artifact_hashes = {
        name: file_content_digest(release_dir / name)
        for name in artifacts_written
        if (release_dir / name).is_file()
    }
    handoffs_written = [
        name
        for name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME)
        if (release_dir / name).is_file()
    ]

    trace_hash: str | None = None
    certificate_id: str | None = None
    certified_bundle_hash: str | None = None

    trace_path = release_dir / "trace.json"
    if trace_path.is_file():
        trace_doc = json.loads(trace_path.read_text(encoding="utf-8"))
        trace_hash = trace_doc.get("trace_hash")

    cert_path = release_dir / "trace_certificate.json"
    if cert_path.is_file():
        cert_doc = json.loads(cert_path.read_text(encoding="utf-8"))
        certificate_id = cert_doc.get("certificate_id")

    certified_path = release_dir / "science_claim_bundle.certified.json"
    if certified_path.is_file():
        certified_bundle_hash = file_content_digest(certified_path)

    return RegenerationReport(
        workflow_id=workflow_id,
        artifacts_written=artifacts_written,
        artifact_hashes=artifact_hashes,
        handoffs_written=handoffs_written,
        certificate_id=certificate_id,
        trace_hash=trace_hash,
        certified_bundle_hash=certified_bundle_hash,
        duration_ms=duration_ms,
        status=status,
        failure_code=failure_code,
    )


def failed_regeneration_report(
    *,
    workflow_id: str,
    duration_ms: int,
    failure_code: str,
    release_dir: Path | None = None,
) -> RegenerationReport:
    """Partial report when regeneration aborts before a complete package."""
    artifacts_written: list[str] = []
    artifact_hashes: dict[str, str] = {}
    handoffs_written: list[str] = []
    if release_dir is not None and release_dir.is_dir():
        for name in LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS:
            path = release_dir / name
            if path.is_file():
                artifacts_written.append(name)
                artifact_hashes[name] = file_content_digest(path)
        for name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_TO_PF_NAME):
            if (release_dir / name).is_file():
                handoffs_written.append(name)
    return RegenerationReport(
        workflow_id=workflow_id,
        artifacts_written=artifacts_written,
        artifact_hashes=artifact_hashes,
        handoffs_written=handoffs_written,
        duration_ms=duration_ms,
        status="failed",
        failure_code=failure_code,
    )


class RegenerationTimer:
    """Record elapsed milliseconds for regeneration reports."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.duration_ms: int = 0

    def __enter__(self) -> RegenerationTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.duration_ms = int((time.perf_counter() - self._start) * 1000)
