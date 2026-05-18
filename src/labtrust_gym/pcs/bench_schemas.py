"""JSON Schema validation for pcs-bench machine-readable artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.policy.loader import load_json, validate_against_schema

FAILURE_CASE_MANIFEST_SCHEMA = (
    "policy/schemas/pcs/FailureCaseManifest.v0.schema.json"
)
REGENERATION_REPORT_SCHEMA = "policy/schemas/pcs/RegenerationReport.v0.schema.json"


def _schema_path(rel: str, *, policy_root: Path | None = None) -> Path:
    root = policy_root or get_repo_root()
    path = root / rel
    if not path.is_file():
        raise FileNotFoundError(f"PCS bench schema not found: {path}")
    return path


def validate_failure_case_manifest(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    """Raise ``PolicyLoadError`` when ``doc`` is not FailureCaseManifest.v0."""
    schema_path = _schema_path(FAILURE_CASE_MANIFEST_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)


def validate_regeneration_report_doc(
    doc: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> None:
    """Raise ``PolicyLoadError`` when ``doc`` is not RegenerationReport.v0."""
    schema_path = _schema_path(REGENERATION_REPORT_SCHEMA, policy_root=policy_root)
    validate_against_schema(doc, load_json(schema_path), path=schema_path)
