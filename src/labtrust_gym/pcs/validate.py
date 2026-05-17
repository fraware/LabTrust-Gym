"""Validate PCS artifacts via pcs-core plus LabTrust integrity rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.integrity import validate_run_directory, validate_trace_document
from labtrust_gym.pcs.schema_version import (
    SCHEMA_VERSION,
    assert_schema_version,
    assert_science_claim_bundle_versions,
)


class PcsValidationError(Exception):
    """Validation failed; see errors list."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = list(errors or [])


def pcs_core_available() -> bool:
    try:
        import pcs_core.validate  # noqa: F401

        return True
    except ImportError:
        return False


def require_pcs_core() -> None:
    if not pcs_core_available():
        raise RuntimeError(
            "pcs-core is required; install with: pip install -e /path/to/pcs-core/python or scripts/setup_pcs_dev.ps1"
        )


def _pcs_validate_artifact(artifact: dict[str, Any]) -> None:
    from pcs_core.validate import ValidationError, validate_artifact

    try:
        validate_artifact(artifact)
    except ValidationError as e:
        raise PcsValidationError(str(e), errors=list(e.errors)) from e


def validate_pcs_artifact(artifact: dict[str, Any], policy_root: Path | None = None) -> None:
    """Schema + semantic validation (pcs-core). policy_root unused; kept for API stability."""
    _ = policy_root
    if artifact.get("bundle_id") and artifact.get("claim_artifact"):
        assert_science_claim_bundle_versions(artifact)
    elif "receipt_id" in artifact:
        assert_schema_version(artifact)
    elif artifact.get("schema_version") is not None:
        assert_schema_version(artifact)
    if pcs_core_available():
        _pcs_validate_artifact(artifact)
    else:
        raise RuntimeError("pcs-core not installed; cannot validate PCS artifact")


def validate_runtime_receipt(artifact: dict[str, Any], policy_root: Path | None = None) -> None:
    _ = policy_root
    assert_schema_version(artifact)
    for key in ("run_outcome", "final_reason_code", "released"):
        if key not in artifact:
            raise PcsValidationError(f"RuntimeReceipt missing required field {key!r}")
    validate_pcs_artifact(artifact)


def validate_science_claim_bundle(bundle: dict[str, Any], policy_root: Path | None = None) -> None:
    _ = policy_root
    assert_science_claim_bundle_versions(bundle)
    validate_pcs_artifact(bundle)


def validate_trace(trace: dict[str, Any]) -> None:
    errors = validate_trace_document(trace)
    if errors:
        raise PcsValidationError("trace validation failed", errors=errors)


def validate_artifact_file(path: Path) -> str:
    """Validate a JSON file; return detected pcs-core artifact type."""
    require_pcs_core()
    from pcs_core.validate import ValidationError, validate_file

    try:
        return validate_file(path)
    except ValidationError as e:
        raise PcsValidationError(str(e), errors=list(e.errors)) from e


def validate_run_dir(run_dir: Path, *, policy_root: Path | None = None) -> None:
    _ = policy_root
    errors = validate_run_directory(run_dir)
    pcs_dir = run_dir / "pcs"
    for name in ("runtime_receipt.json", "science_claim_bundle.pending.json"):
        p = pcs_dir / name
        if p.is_file():
            artifact = json.loads(p.read_text(encoding="utf-8"))
            try:
                validate_pcs_artifact(artifact)
            except (PcsValidationError, RuntimeError) as e:
                msg = getattr(e, "errors", None) or [str(e)]
                errors.extend(f"{name}: {m}" for m in msg)
    if errors:
        raise PcsValidationError(f"run directory {run_dir} failed integrity checks", errors=errors)


def validate_all_schema_versions_v0(bundle: dict[str, Any]) -> None:
    assert_science_claim_bundle_versions(bundle)
    if bundle.get("schema_version") != SCHEMA_VERSION:
        raise PcsValidationError("top-level schema_version must be v0")
