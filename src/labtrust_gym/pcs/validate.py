"""Validate PCS artifacts against bundled schemas or optional pcs-core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from labtrust_gym.config import get_repo_root, policy_path

SCHEMA_MAP: dict[str, str] = {
    "Trace": "trace.v0.schema.json",
    "RuntimeReceipt": "runtime_receipt.v0.schema.json",
    "EvidenceBundle": "evidence_bundle.v0.schema.json",
    "AssumptionSet": "assumption_set.v0.schema.json",
    "ClaimArtifact": "claim_artifact.v0.schema.json",
    "ScienceClaimBundle": "science_claim_bundle.v0.schema.json",
    "TraceCertificate": "trace_certificate.v0.schema.json",
}


def _schema_dir(policy_root: Path | None = None) -> Path:
    root = policy_root or get_repo_root()
    return policy_path(root, "schemas", "pcs")


def load_schema(artifact_kind: str, policy_root: Path | None = None) -> dict[str, Any]:
    try:
        from pcs_core.artifact import ARTIFACT_SCHEMAS, schemas_dir

        schema_name = ARTIFACT_SCHEMAS.get(f"{artifact_kind}.v0") or ARTIFACT_SCHEMAS.get(
            artifact_kind
        )
        if schema_name:
            path = schemas_dir() / schema_name
            return json.loads(path.read_text(encoding="utf-8"))
    except ImportError:
        pass
    filename = SCHEMA_MAP.get(artifact_kind)
    if not filename:
        raise KeyError(f"no schema for {artifact_kind}")
    path = _schema_dir(policy_root) / filename
    return json.loads(path.read_text(encoding="utf-8"))


def _detect_kind(artifact: dict[str, Any]) -> str:
    try:
        from pcs_core.artifact import detect_artifact_type

        detected = detect_artifact_type(artifact)
        if detected:
            return detected.replace(".v0", "")
    except ImportError:
        pass
    kind = artifact.get("artifact_kind")
    if kind:
        return str(kind)
    raise ValueError("could not detect artifact type")


def validate_with_jsonschema(artifact: dict[str, Any], policy_root: Path | None = None) -> None:
    kind = _detect_kind(artifact)
    schema = load_schema(kind, policy_root)
    Draft202012Validator(schema).validate(artifact)


def validate_pcs_artifact(artifact: dict[str, Any], policy_root: Path | None = None) -> None:
    """Validate using pcs-core when installed, else local JSON Schema."""
    try:
        from pcs_core.validate import validate_artifact  # type: ignore[import-untyped]

        validate_artifact(artifact)
    except ImportError:
        validate_with_jsonschema(artifact, policy_root)
