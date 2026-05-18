"""Atomic PCS release-run staging, handoff manifests, and promotion to ``release/``."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.manifest import (
    PLACEHOLDER_COMMITS,
    _git_head,
    resolve_pcs_core_root,
    validate_release_manifest,
)
from labtrust_gym.pcs.release_provenance import validate_release_artifact_provenance

HANDOFF_ARTIFACTS: tuple[str, ...] = (
    "trace.json",
    "runtime_receipt.json",
    "trace_certificate.json",
    "science_claim_bundle.pending.json",
    "science_claim_bundle.certified.json",
)

DOWNSTREAM_ARTIFACTS: tuple[str, ...] = (
    "verification_result.json",
    "signed_science_claim_bundle.json",
    "scientific_memory_import_report.json",
)

RELEASE_HANDOFF_MANIFEST_NAME = "RELEASE_HANDOFF_MANIFEST.json"
HANDOFF_TO_PF_NAME = "handoff_to_pf.json"
HANDOFF_TO_CERTIFYEDGE_NAME = "handoff_to_certifyedge.json"
HANDOFF_FOR_PF_NAME = HANDOFF_TO_PF_NAME  # deprecated alias
RELEASE_FIXTURE_MANIFEST_NAME = "RELEASE_FIXTURE_MANIFEST.json"
LEGACY_MANIFEST_NAME = "manifest.json"

RELEASE_RUN_REL = Path("examples/pcs_qc_release/release-run")
RELEASE_REL = Path("examples/pcs_qc_release/release")
HANDOFF_REL = Path("examples/pcs_qc_release/release/handoff")


def release_run_dir(policy_root: Path | None = None) -> Path:
    return (policy_root or get_repo_root()) / RELEASE_RUN_REL


def release_fixture_dir(policy_root: Path | None = None) -> Path:
    return (policy_root or get_repo_root()) / RELEASE_REL


def handoff_dir(policy_root: Path | None = None) -> Path:
    return release_fixture_dir(policy_root) / "handoff"


def file_content_digest(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_provability_fabric_root(labtrust_root: Path | None = None) -> Path:
    root = labtrust_root or get_repo_root()
    raw = os.environ.get("PROVABILITY_FABRIC_ROOT", "").strip()
    if raw:
        return Path(raw)
    candidate = root.parent / "provability-fabric"
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError("provability-fabric not found; set PROVABILITY_FABRIC_ROOT")


def resolve_scientific_memory_root(labtrust_root: Path | None = None) -> Path:
    root = labtrust_root or get_repo_root()
    raw = os.environ.get("SCIENTIFIC_MEMORY_ROOT", "").strip()
    if raw:
        return Path(raw)
    candidate = root.parent / "scientific-memory"
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError("scientific-memory not found; set SCIENTIFIC_MEMORY_ROOT")


def resolve_release_repo_commits(
    labtrust_root: Path | None = None,
    *,
    certifyedge_root: Path | None = None,
    pcs_core_root: Path | None = None,
    provability_fabric_root: Path | None = None,
    scientific_memory_root: Path | None = None,
    require_pf: bool = False,
    require_sm: bool = False,
) -> dict[str, str]:
    """Resolve git HEAD for all repos participating in a release run."""
    lt = labtrust_root or get_repo_root()
    ce = certifyedge_root or (lt.parent / "CertifyEdge")
    pc = pcs_core_root or resolve_pcs_core_root(lt)

    commits = {
        "labtrust_gym_commit": _git_head(lt),
        "certifyedge_commit": _git_head(ce),
        "pcs_core_commit": _git_head(pc),
    }

    if require_pf:
        pf = provability_fabric_root or resolve_provability_fabric_root(lt)
        commits["provability_fabric_commit"] = _git_head(pf)
    if require_sm:
        sm = scientific_memory_root or resolve_scientific_memory_root(lt)
        commits["scientific_memory_commit"] = _git_head(sm)

    for label, commit in commits.items():
        if commit in PLACEHOLDER_COMMITS or len(commit) < 12:
            raise ValueError(f"{label} must be a real git SHA, got {commit!r}")
    return commits


def certified_bundle_ids(certified: dict[str, Any]) -> tuple[str, str, str]:
    bundle_id = certified["bundle_id"]
    certificate_id = certified["certificates"][0]["certificate_id"]
    trace_hash = certified["runtime_receipts"][0]["trace_hash"]
    return bundle_id, certificate_id, trace_hash


def certificate_id_from_verification(verification: dict[str, Any]) -> str:
    for check in verification.get("checks", []):
        if check.get("check_id") == "evidence_refs_complete":
            refs = check.get("details", {}).get("certificate_refs", [])
            if refs:
                return refs[0]
    raise ValueError("verification_result.json missing evidence_refs_complete.certificate_refs[0]")


def validate_certificate_id_chain(run_dir: Path) -> None:
    """Certified bundle, PF verification, and signed bundle must share one certificate_id."""
    certified_path = run_dir / "science_claim_bundle.certified.json"
    if not certified_path.is_file():
        raise FileNotFoundError(f"missing {certified_path.name}")

    certified = _load_json(certified_path)
    _, cert_id, _ = certified_bundle_ids(certified)

    verification_path = run_dir / "verification_result.json"
    if verification_path.is_file():
        verification = _load_json(verification_path)
        vf_id = certificate_id_from_verification(verification)
        if vf_id != cert_id:
            raise ValueError(
                f"verification_result certificate_id {vf_id!r} != "
                f"science_claim_bundle.certified {cert_id!r}"
            )

    signed_path = run_dir / "signed_science_claim_bundle.json"
    if signed_path.is_file():
        signed = _load_json(signed_path)
        bundle = signed.get("science_claim_bundle", signed)
        signed_id = bundle["certificates"][0]["certificate_id"]
        if signed_id != cert_id:
            raise ValueError(
                f"signed_science_claim_bundle certificate_id {signed_id!r} != "
                f"science_claim_bundle.certified {cert_id!r} (stale PF sign input)"
            )


def build_handoff_manifest(
    run_dir: Path,
    commits: dict[str, str],
    *,
    generator: str,
    handoff_id: str | None = None,
) -> dict[str, Any]:
    certified = _load_json(run_dir / "science_claim_bundle.certified.json")
    bundle_id, certificate_id, trace_hash = certified_bundle_ids(certified)
    artifact_digests = {name: file_content_digest(run_dir / name) for name in HANDOFF_ARTIFACTS}

    manifest: dict[str, Any] = {
        "schema_version": "v0",
        "handoff_id": handoff_id
        or f"labtrust-qc-release-v0.1-{commits['labtrust_gym_commit'][:12]}",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": generator,
        "labtrust_gym_commit": commits["labtrust_gym_commit"],
        "certifyedge_commit": commits["certifyedge_commit"],
        "pcs_core_commit": commits["pcs_core_commit"],
        "certified_bundle_id": bundle_id,
        "certificate_id": certificate_id,
        "trace_hash": trace_hash,
        "artifacts": artifact_digests,
    }
    return manifest


def build_handoff_for_pf(
    run_dir: Path,
    *,
    source_commit: str | None = None,
) -> dict[str, Any]:
    """Build HandoffManifest.v0 for PF signing (legacy name retained for callers)."""
    from labtrust_gym.pcs.handoff_manifest import build_bundle_to_verifier_handoff

    return build_bundle_to_verifier_handoff(
        run_dir / "science_claim_bundle.certified.json",
        release_mode=True,
        source_commit=source_commit,
    )


def build_handoff_for_certifyedge(
    run_dir: Path,
    *,
    source_commit: str | None = None,
) -> dict[str, Any]:
    """Build HandoffManifest.v0 for CertifyEdge certificate emission."""
    from labtrust_gym.pcs.handoff_manifest import build_runtime_to_certificate_handoff

    return build_runtime_to_certificate_handoff(
        run_dir / "trace.json",
        receipt_path=run_dir / "runtime_receipt.json",
        release_mode=True,
        source_commit=source_commit,
    )


def build_release_fixture_manifest(
    run_dir: Path,
    commits: dict[str, str],
    handoff_manifest: dict[str, Any],
    *,
    generator: str,
) -> dict[str, Any]:
    artifact_digests: dict[str, str] = dict(handoff_manifest["artifacts"])
    for name in DOWNSTREAM_ARTIFACTS:
        path = run_dir / name
        if path.is_file():
            artifact_digests[name] = file_content_digest(path)

    manifest: dict[str, Any] = {
        "schema_version": "v0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": generator,
        "handoff_id": handoff_manifest["handoff_id"],
        "labtrust_gym_commit": commits["labtrust_gym_commit"],
        "certifyedge_commit": commits["certifyedge_commit"],
        "pcs_core_commit": commits["pcs_core_commit"],
        "certificate_id": handoff_manifest["certificate_id"],
        "trace_hash": handoff_manifest["trace_hash"],
        "certified_bundle_id": handoff_manifest["certified_bundle_id"],
        "artifacts": artifact_digests,
    }
    if "provability_fabric_commit" in commits:
        manifest["provability_fabric_commit"] = commits["provability_fabric_commit"]
    if "scientific_memory_commit" in commits:
        manifest["scientific_memory_commit"] = commits["scientific_memory_commit"]
    return manifest


def write_run_manifests(
    run_dir: Path,
    commits: dict[str, str],
    *,
    generator: str,
    handoff_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Write RELEASE_HANDOFF_MANIFEST, HandoffManifest.v0, and RELEASE_FIXTURE_MANIFEST into run_dir."""
    for name in HANDOFF_ARTIFACTS:
        if not (run_dir / name).is_file():
            raise FileNotFoundError(f"release-run missing handoff artifact: {name}")

    validate_certificate_id_chain(run_dir)

    handoff_manifest = build_handoff_manifest(
        run_dir, commits, generator=generator, handoff_id=handoff_id
    )
    handoff_pf = build_handoff_for_pf(run_dir, source_commit=commits["labtrust_gym_commit"])
    handoff_ce = build_handoff_for_certifyedge(run_dir, source_commit=commits["labtrust_gym_commit"])
    fixture_manifest = build_release_fixture_manifest(
        run_dir, commits, handoff_manifest, generator=generator
    )

    (run_dir / RELEASE_HANDOFF_MANIFEST_NAME).write_text(
        json.dumps(handoff_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / HANDOFF_TO_CERTIFYEDGE_NAME).write_text(
        json.dumps(handoff_ce, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / HANDOFF_FOR_PF_NAME).write_text(
        json.dumps(handoff_pf, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (run_dir / RELEASE_FIXTURE_MANIFEST_NAME).write_text(
        json.dumps(fixture_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return handoff_manifest, handoff_pf, fixture_manifest


def _write_legacy_release_manifest(
    release_root: Path,
    handoff_manifest: dict[str, Any],
    *,
    generator: str,
    certifyedge_bin: str,
    certifyedge_spec: str,
) -> dict[str, Any]:
    """Write canonical ``release/manifest.json`` and ``release/handoff_to_pf.json``."""
    from labtrust_gym.pcs.release_handoff import build_canonical_release_manifest, build_pf_handoff

    manifest = build_canonical_release_manifest(
        release_root,
        handoff_manifest,
        generator=generator,
        certifyedge_bin=certifyedge_bin,
        certifyedge_spec=certifyedge_spec,
    )
    build_pf_handoff(release_root, manifest)
    return manifest


def validate_handoff_directory(handoff_root: Path) -> None:
    for name in HANDOFF_ARTIFACTS:
        if not (handoff_root / name).is_file():
            raise FileNotFoundError(f"handoff missing: {name}")
    manifest_path = handoff_root / RELEASE_HANDOFF_MANIFEST_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"handoff missing: {RELEASE_HANDOFF_MANIFEST_NAME}")
    manifest = _load_json(manifest_path)
    for name, expected_digest in manifest.get("artifacts", {}).items():
        path = handoff_root / name
        if file_content_digest(path) != expected_digest:
            raise ValueError(f"handoff digest mismatch for {name}")
    from labtrust_gym.pcs.handoff_manifest import assert_handoff_manifest_valid

    handoff_path = handoff_root / HANDOFF_TO_PF_NAME
    if not handoff_path.is_file():
        raise FileNotFoundError(f"handoff missing: {HANDOFF_TO_PF_NAME}")
    legacy_guard = handoff_root / "handoff_for_pf.json"
    if legacy_guard.is_file() and legacy_guard != handoff_path:
        raise ValueError(
            "handoff/ must not contain legacy handoff_for_pf.json; use handoff_to_pf.json"
        )
    from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_CERTIFYEDGE_NAME as CE_HANDOFF

    ce_path = handoff_root / CE_HANDOFF
    if ce_path.is_file():
        assert_handoff_manifest_valid(_load_json(ce_path))

    pf_doc = _load_json(handoff_path)
    assert_handoff_manifest_valid(pf_doc)
    certified_name = "science_claim_bundle.certified.json"
    certified = _load_json(handoff_root / certified_name)
    _, cert_id, trace_hash = certified_bundle_ids(certified)
    inv = pf_doc.get("invariants") or {}
    if inv.get("certificate_id") != cert_id:
        raise ValueError("handoff_to_pf invariants.certificate_id mismatch")
    if inv.get("trace_hash") != trace_hash:
        raise ValueError("handoff_to_pf invariants.trace_hash mismatch")
    entry = (pf_doc.get("input_artifacts") or {}).get(certified_name) or {}
    on_disk = file_content_digest(handoff_root / certified_name)
    if entry.get("sha256") != on_disk:
        raise ValueError("handoff_to_pf input_artifacts certified bundle sha256 mismatch")


def promote_release_run_atomic(
    run_dir: Path,
    release_root: Path | None = None,
    *,
    generator: str,
    certifyedge_bin: str = "certifyedge",
    certifyedge_spec: str = "",
) -> Path:
    """
    Atomically promote a complete release-run directory into ``release/`` and ``release/handoff/``.

    Copies handoff artifacts + manifests into ``handoff/``, flat LabTrust/CertifyEdge artifacts
  into ``release/``, optional downstream PF/SM artifacts when present, then validates.
    """
    from labtrust_gym.pcs.release_fixtures import write_trace_hash_alignment

    run_dir = run_dir.resolve()
    release_root = (release_root or release_fixture_dir()).resolve()
    handoff_root = release_root / "handoff"

    handoff_manifest_path = run_dir / RELEASE_HANDOFF_MANIFEST_NAME
    if not handoff_manifest_path.is_file():
        raise FileNotFoundError(
            f"run_dir missing {RELEASE_HANDOFF_MANIFEST_NAME}; call write_run_manifests first"
        )
    handoff_manifest = _load_json(handoff_manifest_path)

    staging_handoff = run_dir / "_promote_handoff"
    staging_release = run_dir / "_promote_release"
    for path in (staging_handoff, staging_release):
        if path.exists():
            shutil.rmtree(path)
    staging_handoff.mkdir(parents=True)
    staging_release.mkdir(parents=True)

    try:
        for name in HANDOFF_ARTIFACTS:
            shutil.copy2(run_dir / name, staging_handoff / name)
        for extra in (
            RELEASE_HANDOFF_MANIFEST_NAME,
            HANDOFF_TO_CERTIFYEDGE_NAME,
            HANDOFF_FOR_PF_NAME,
        ):
            src_extra = run_dir / extra
            if src_extra.is_file():
                shutil.copy2(src_extra, staging_handoff / extra)

        for name in HANDOFF_ARTIFACTS:
            shutil.copy2(run_dir / name, staging_release / name)
        for name in DOWNSTREAM_ARTIFACTS:
            src = run_dir / name
            if src.is_file():
                shutil.copy2(src, staging_release / name)

        if (run_dir / RELEASE_FIXTURE_MANIFEST_NAME).is_file():
            shutil.copy2(run_dir / RELEASE_FIXTURE_MANIFEST_NAME, staging_release / RELEASE_FIXTURE_MANIFEST_NAME)

        validate_handoff_directory(staging_handoff)
        validate_certificate_id_chain(staging_release)

        if handoff_root.exists():
            shutil.rmtree(handoff_root)
        shutil.move(str(staging_handoff), str(handoff_root))

        for name in HANDOFF_ARTIFACTS + DOWNSTREAM_ARTIFACTS:
            dest = release_root / name
            src = staging_release / name
            if src.is_file():
                if dest.exists():
                    dest.unlink()
                shutil.copy2(src, dest)

        if (staging_release / RELEASE_FIXTURE_MANIFEST_NAME).is_file():
            shutil.copy2(
                staging_release / RELEASE_FIXTURE_MANIFEST_NAME,
                release_root / RELEASE_FIXTURE_MANIFEST_NAME,
            )

        _write_legacy_release_manifest(
            release_root,
            handoff_manifest,
            generator=generator,
            certifyedge_bin=certifyedge_bin,
            certifyedge_spec=certifyedge_spec,
        )
        for handoff_name in (HANDOFF_TO_CERTIFYEDGE_NAME, HANDOFF_FOR_PF_NAME):
            src = run_dir / handoff_name
            if src.is_file():
                shutil.copy2(src, release_root / handoff_name)
                shutil.copy2(src, handoff_root / handoff_name)
        write_trace_hash_alignment(release_root)

        legacy_manifest = _load_json(release_root / LEGACY_MANIFEST_NAME)
        validate_release_manifest(legacy_manifest)
        validate_release_artifact_provenance(release_root, legacy_manifest)

        from labtrust_gym.pcs.release_handoff import verify_release_handoff

        verify_release_handoff(release_root)

        signed = release_root / "signed_science_claim_bundle.json"
        if signed.is_file():
            validate_certificate_id_chain(release_root)
    finally:
        for path in (staging_handoff, staging_release):
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

    return release_root


def prepare_staging_run_dir(staging: Path) -> Path:
    """Create an empty staging directory for a new release run."""
    staging = staging.resolve()
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    return staging
