"""PCS HandoffManifest.v0 emission and validation (LabTrust → Provability Fabric)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import is_release_fixture_mode
from labtrust_gym.pcs.hash import pcs_digest
from labtrust_gym.pcs.manifest import PLACEHOLDER_COMMITS, _git_head, resolve_pcs_core_root
from labtrust_gym.pcs.provenance import LOCAL_DEV_COMMIT, SOURCE_REPO, resolve_source_commit
from labtrust_gym.pcs.release_run import certified_bundle_ids, file_content_digest

HANDOFF_TO_PF_NAME = "handoff_to_pf.json"
CERTIFIED_BUNDLE_NAME = "science_claim_bundle.certified.json"
HANDOFF_KIND_BUNDLE_TO_VERIFIER = "bundle_to_verifier"
FROM_COMPONENT = "LabTrust-Gym"
TO_COMPONENT = "Provability Fabric"
DEFAULT_HANDOFF_ID = "handoff-labtrust-to-pf-qc-release-v0.1"

_KIND_ALIASES: dict[str, str] = {
    "bundle-to-verifier": HANDOFF_KIND_BUNDLE_TO_VERIFIER,
    "bundle_to_verifier": HANDOFF_KIND_BUNDLE_TO_VERIFIER,
}


def normalize_handoff_kind(kind: str) -> str:
    normalized = _KIND_ALIASES.get(kind.strip().lower())
    if normalized is None:
        raise ValueError(f"unsupported handoff kind: {kind!r}")
    return normalized


def handoff_manifest_schema_path() -> Path:
    return resolve_pcs_core_root() / "schemas" / "HandoffManifest.v0.schema.json"


def handoff_manifest_registry():
    from pcs_core.validate import get_registry

    return get_registry()


def validate_handoff_manifest_v0(doc: dict[str, Any]) -> list[str]:
    """Validate against pcs-core ``HandoffManifest.v0.schema.json``."""
    schema_path = handoff_manifest_schema_path()
    if not schema_path.is_file():
        raise FileNotFoundError(f"HandoffManifest schema not found: {schema_path}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=handoff_manifest_registry())
    return sorted(e.message for e in validator.iter_errors(doc))


def assert_handoff_manifest_valid(doc: dict[str, Any]) -> None:
    errors = validate_handoff_manifest_v0(doc)
    if errors:
        raise ValueError("HandoffManifest.v0 validation failed: " + "; ".join(errors))


def assert_release_mode_handoff_provenance(doc: dict[str, Any]) -> None:
    """Release evidence handoffs must not use local-dev or placeholder source commits."""
    commit = doc.get("source_commit", "")
    if commit == LOCAL_DEV_COMMIT:
        raise ValueError("HandoffManifest source_commit must not be local-dev in release mode")
    if commit in PLACEHOLDER_COMMITS:
        raise ValueError(f"HandoffManifest source_commit must not be placeholder: {commit!r}")
    if doc.get("local_dev") is True:
        raise ValueError("HandoffManifest must not set local_dev in release mode")


def build_bundle_to_verifier_handoff(
    bundle_path: Path,
    *,
    policy_root: Path | None = None,
    handoff_id: str = DEFAULT_HANDOFF_ID,
    release_mode: bool | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    """
    Build HandoffManifest.v0 for LabTrust certified bundle → Provability Fabric.

    ``release_mode`` defaults to ``PCS_RELEASE_FIXTURE`` env or true when bundle lives under
    ``examples/pcs_qc_release/release/``.
    """
    bundle_path = bundle_path.resolve()
    if not bundle_path.is_file():
        raise FileNotFoundError(f"certified bundle not found: {bundle_path}")

    root = policy_root or get_repo_root()
    if release_mode is None:
        release_mode = is_release_fixture_mode() or "release" in bundle_path.as_posix()

    certified = json.loads(bundle_path.read_text(encoding="utf-8"))
    _, certificate_id, trace_hash = certified_bundle_ids(certified)
    bundle_hash = file_content_digest(bundle_path)

    if source_commit is None:
        if release_mode:
            source_commit = _git_head(root)
        else:
            resolved, local_dev = resolve_source_commit(root)
            if local_dev:
                raise ValueError("HandoffManifest requires a git checkout (non-local-dev source_commit)")
            source_commit = resolved

    if release_mode:
        assert_release_mode_handoff_provenance({"source_commit": source_commit})

    doc: dict[str, Any] = {
        "schema_version": "v0",
        "handoff_id": handoff_id,
        "handoff_kind": HANDOFF_KIND_BUNDLE_TO_VERIFIER,
        "from_component": FROM_COMPONENT,
        "to_component": TO_COMPONENT,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_repo": SOURCE_REPO,
        "source_commit": source_commit,
        "input_artifacts": {
            CERTIFIED_BUNDLE_NAME: {
                "artifact_type": "ScienceClaimBundle.v0",
                "sha256": bundle_hash,
            }
        },
        "expected_outputs": {
            "verification_result.json": {"artifact_type": "VerificationResult.v0"},
            "signed_science_claim_bundle.json": {"artifact_type": "SignedScienceClaimBundle.v0"},
        },
        "invariants": {
            "certificate_id": certificate_id,
            "trace_hash": trace_hash,
            "certified_bundle_hash": bundle_hash,
        },
        "status": "Validated",
    }
    doc["signature_or_digest"] = pcs_digest(doc)
    return doc


def emit_handoff_manifest(
    *,
    kind: str,
    bundle_path: Path,
    out_path: Path,
    policy_root: Path | None = None,
    handoff_id: str = DEFAULT_HANDOFF_ID,
    release_mode: bool | None = None,
) -> dict[str, Any]:
    """Write HandoffManifest.v0 to ``out_path``."""
    handoff_kind = normalize_handoff_kind(kind)
    if handoff_kind != HANDOFF_KIND_BUNDLE_TO_VERIFIER:
        raise ValueError(f"only bundle_to_verifier is implemented, got {handoff_kind!r}")

    doc = build_bundle_to_verifier_handoff(
        bundle_path,
        policy_root=policy_root,
        handoff_id=handoff_id,
        release_mode=release_mode,
    )
    assert_handoff_manifest_valid(doc)
    if release_mode is None:
        release_mode = is_release_fixture_mode() or "release" in bundle_path.as_posix()
    if release_mode:
        assert_release_mode_handoff_provenance(doc)

    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def build_handoff_to_pf_from_release(
    release_root: Path,
    manifest: dict[str, Any],
    *,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    """Write ``handoff_to_pf.json`` using release manifest invariants and certified bundle bytes."""
    release_root = release_root.resolve()
    bundle_path = release_root / CERTIFIED_BUNDLE_NAME
    handoff_id = manifest.get("handoff_id", DEFAULT_HANDOFF_ID)
    if not str(handoff_id).startswith("handoff-"):
        handoff_id = DEFAULT_HANDOFF_ID

    doc = build_bundle_to_verifier_handoff(
        bundle_path,
        policy_root=policy_root,
        handoff_id=handoff_id,
        release_mode=True,
        source_commit=manifest["labtrust_gym_commit"],
    )
    invariants = doc["invariants"]
    invariants["certificate_id"] = manifest["certificate_id"]
    invariants["trace_hash"] = manifest["trace_hash"]
    invariants["certified_bundle_hash"] = manifest["certified_bundle_hash"]
    doc.pop("signature_or_digest", None)
    doc["signature_or_digest"] = pcs_digest(doc)

    out_path = release_root / HANDOFF_TO_PF_NAME
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc
