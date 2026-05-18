"""PCS HandoffManifest.v0 emission and validation (LabTrust runtime protocol producer)."""

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
HANDOFF_TO_CERTIFYEDGE_NAME = "handoff_to_certifyedge.json"
CERTIFIED_BUNDLE_NAME = "science_claim_bundle.certified.json"
TRACE_NAME = "trace.json"
RUNTIME_RECEIPT_NAME = "runtime_receipt.json"
TRACE_CERTIFICATE_NAME = "trace_certificate.json"

HANDOFF_KIND_BUNDLE_TO_VERIFIER = "bundle_to_verifier"
HANDOFF_KIND_RUNTIME_TO_CERTIFICATE = "runtime_to_certificate"
FROM_COMPONENT = "LabTrust-Gym"
TO_COMPONENT_PF = "Provability Fabric"
TO_COMPONENT_CERTIFYEDGE = "CertifyEdge"
DEFAULT_HANDOFF_ID_PF = "handoff-labtrust-to-pf-qc-release-v0.1"
DEFAULT_HANDOFF_ID_CE = "handoff-labtrust-runtime-to-certifyedge-rc"
DEFAULT_PROPERTY_ID = "hospital_lab.qc_release"

_KIND_ALIASES: dict[str, str] = {
    "bundle-to-verifier": HANDOFF_KIND_BUNDLE_TO_VERIFIER,
    "bundle_to_verifier": HANDOFF_KIND_BUNDLE_TO_VERIFIER,
    "runtime-to-certificate": HANDOFF_KIND_RUNTIME_TO_CERTIFICATE,
    "runtime_to_certificate": HANDOFF_KIND_RUNTIME_TO_CERTIFICATE,
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


def assert_handoff_registry_check(path: Path) -> None:
    """Run ``pcs registry check-artifact`` semantics on a HandoffManifest file."""
    from pcs_core.registry import check_artifact_against_registry

    drift = check_artifact_against_registry(path.resolve())
    if drift:
        raise ValueError(f"registry check failed for {path.name}: " + "; ".join(drift))


def assert_release_mode_handoff_provenance(doc: dict[str, Any]) -> None:
    """Release evidence handoffs must not use local-dev or placeholder source commits."""
    commit = doc.get("source_commit", "")
    if commit == LOCAL_DEV_COMMIT:
        raise ValueError("HandoffManifest source_commit must not be local-dev in release mode")
    if commit in PLACEHOLDER_COMMITS:
        raise ValueError(f"HandoffManifest source_commit must not be placeholder: {commit!r}")
    if doc.get("local_dev") is True:
        raise ValueError("HandoffManifest must not set local_dev in release mode")


def _resolve_source_commit(
    policy_root: Path,
    *,
    release_mode: bool,
    source_commit: str | None,
) -> str:
    if source_commit is not None:
        return source_commit
    if release_mode:
        return _git_head(policy_root)
    resolved, local_dev = resolve_source_commit(policy_root)
    if local_dev:
        raise ValueError("HandoffManifest requires a git checkout (non-local-dev source_commit)")
    return resolved


def _finalize_handoff_doc(doc: dict[str, Any], *, release_mode: bool) -> dict[str, Any]:
    if release_mode:
        assert_release_mode_handoff_provenance(doc)
    doc["signature_or_digest"] = pcs_digest(doc)
    assert_handoff_manifest_valid(doc)
    return doc


def build_runtime_to_certificate_handoff(
    trace_path: Path,
    *,
    receipt_path: Path | None = None,
    policy_root: Path | None = None,
    handoff_id: str = DEFAULT_HANDOFF_ID_CE,
    release_mode: bool | None = None,
    source_commit: str | None = None,
    property_id: str = DEFAULT_PROPERTY_ID,
) -> dict[str, Any]:
    """Build HandoffManifest.v0 for LabTrust trace → CertifyEdge certificate."""
    trace_path = trace_path.resolve()
    if not trace_path.is_file():
        raise FileNotFoundError(f"trace not found: {trace_path}")

    root = policy_root or get_repo_root()
    if release_mode is None:
        release_mode = is_release_fixture_mode() or "release" in trace_path.as_posix()

    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace_hash = trace.get("trace_hash")
    if not trace_hash:
        raise ValueError("trace.json missing trace_hash")

    commit = _resolve_source_commit(root, release_mode=release_mode, source_commit=source_commit)
    if release_mode:
        assert_release_mode_handoff_provenance({"source_commit": commit})

    input_artifacts: dict[str, Any] = {
        TRACE_NAME: {
            "artifact_type": "LabTrust.Trace.v0",
            "sha256": file_content_digest(trace_path),
        }
    }
    if receipt_path is not None:
        receipt_path = receipt_path.resolve()
        if receipt_path.is_file():
            input_artifacts[RUNTIME_RECEIPT_NAME] = {
                "artifact_type": "RuntimeReceipt.v0",
                "sha256": file_content_digest(receipt_path),
            }

    doc: dict[str, Any] = {
        "schema_version": "v0",
        "handoff_id": handoff_id,
        "handoff_kind": HANDOFF_KIND_RUNTIME_TO_CERTIFICATE,
        "from_component": FROM_COMPONENT,
        "to_component": TO_COMPONENT_CERTIFYEDGE,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_repo": SOURCE_REPO,
        "source_commit": commit,
        "input_artifacts": input_artifacts,
        "expected_outputs": {
            TRACE_CERTIFICATE_NAME: {"artifact_type": "TraceCertificate.v0"},
        },
        "invariants": {
            "trace_hash": trace_hash,
            "property_id": property_id,
        },
        "status": "Validated",
    }
    return _finalize_handoff_doc(doc, release_mode=release_mode)


def build_bundle_to_verifier_handoff(
    bundle_path: Path,
    *,
    policy_root: Path | None = None,
    handoff_id: str = DEFAULT_HANDOFF_ID_PF,
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

    commit = _resolve_source_commit(root, release_mode=release_mode, source_commit=source_commit)
    if release_mode:
        assert_release_mode_handoff_provenance({"source_commit": commit})

    doc: dict[str, Any] = {
        "schema_version": "v0",
        "handoff_id": handoff_id,
        "handoff_kind": HANDOFF_KIND_BUNDLE_TO_VERIFIER,
        "from_component": FROM_COMPONENT,
        "to_component": TO_COMPONENT_PF,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_repo": SOURCE_REPO,
        "source_commit": commit,
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
    return _finalize_handoff_doc(doc, release_mode=release_mode)


def emit_handoff_to_certifyedge(
    *,
    trace_path: Path,
    runtime_receipt_path: Path,
    out_path: Path,
    policy_root: Path | None = None,
    property_id: str = DEFAULT_PROPERTY_ID,
    release_mode: bool | None = None,
    handoff_id: str | None = None,
) -> dict[str, Any]:
    """Write ``handoff_to_certifyedge.json`` (runtime_to_certificate HandoffManifest.v0)."""
    return emit_handoff_manifest(
        kind="runtime-to-certificate",
        trace_path=trace_path,
        receipt_path=runtime_receipt_path,
        out_path=out_path,
        policy_root=policy_root,
        property_id=property_id,
        release_mode=release_mode,
        handoff_id=handoff_id,
    )


def emit_handoff_to_pf(
    *,
    bundle_path: Path,
    out_path: Path,
    policy_root: Path | None = None,
    release_mode: bool | None = None,
    handoff_id: str | None = None,
) -> dict[str, Any]:
    """Write ``handoff_to_pf.json`` (bundle_to_verifier HandoffManifest.v0)."""
    return emit_handoff_manifest(
        kind="bundle-to-verifier",
        bundle_path=bundle_path,
        out_path=out_path,
        policy_root=policy_root,
        release_mode=release_mode,
        handoff_id=handoff_id,
    )


def emit_handoff_manifest(
    *,
    kind: str,
    out_path: Path,
    policy_root: Path | None = None,
    handoff_id: str | None = None,
    release_mode: bool | None = None,
    bundle_path: Path | None = None,
    trace_path: Path | None = None,
    receipt_path: Path | None = None,
    property_id: str = DEFAULT_PROPERTY_ID,
) -> dict[str, Any]:
    """Write HandoffManifest.v0 to ``out_path``."""
    handoff_kind = normalize_handoff_kind(kind)
    if handoff_kind == HANDOFF_KIND_BUNDLE_TO_VERIFIER:
        if bundle_path is None:
            raise ValueError("emit-handoff bundle_to_verifier requires --bundle")
        doc = build_bundle_to_verifier_handoff(
            bundle_path,
            policy_root=policy_root,
            handoff_id=handoff_id or DEFAULT_HANDOFF_ID_PF,
            release_mode=release_mode,
        )
    elif handoff_kind == HANDOFF_KIND_RUNTIME_TO_CERTIFICATE:
        if trace_path is None:
            raise ValueError("emit-handoff runtime_to_certificate requires --trace")
        doc = build_runtime_to_certificate_handoff(
            trace_path,
            receipt_path=receipt_path,
            policy_root=policy_root,
            handoff_id=handoff_id or DEFAULT_HANDOFF_ID_CE,
            release_mode=release_mode,
            property_id=property_id,
        )
    else:
        raise ValueError(f"unsupported handoff kind: {handoff_kind!r}")

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
    handoff_id = manifest.get("handoff_id", DEFAULT_HANDOFF_ID_PF)
    if not str(handoff_id).startswith("handoff-"):
        handoff_id = DEFAULT_HANDOFF_ID_PF

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


def build_handoff_to_certifyedge_from_release(
    release_root: Path,
    manifest: dict[str, Any],
    *,
    policy_root: Path | None = None,
    property_id: str = DEFAULT_PROPERTY_ID,
) -> dict[str, Any]:
    """Write ``handoff_to_certifyedge.json`` from release trace + receipt."""
    release_root = release_root.resolve()
    doc = build_runtime_to_certificate_handoff(
        release_root / TRACE_NAME,
        receipt_path=release_root / RUNTIME_RECEIPT_NAME,
        policy_root=policy_root,
        release_mode=True,
        source_commit=manifest["labtrust_gym_commit"],
        property_id=property_id,
    )
    inv = doc["invariants"]
    inv["trace_hash"] = manifest["trace_hash"]
    doc.pop("signature_or_digest", None)
    doc["signature_or_digest"] = pcs_digest(doc)

    out_path = release_root / HANDOFF_TO_CERTIFYEDGE_NAME
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc
