"""Sync LabTrust ``release/`` fixtures from canonical ``pcs-core/examples/labtrust-release/``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.manifest import resolve_pcs_core_root
from labtrust_gym.pcs.release_handoff import (
    build_canonical_release_manifest,
    build_pf_handoff,
    verify_release_handoff,
)
from labtrust_gym.pcs.release_run import (
    HANDOFF_ARTIFACTS,
    HANDOFF_FOR_PF_NAME,
    RELEASE_FIXTURE_MANIFEST_NAME,
    RELEASE_HANDOFF_MANIFEST_NAME,
    DOWNSTREAM_ARTIFACTS,
    build_handoff_for_pf,
    build_handoff_manifest,
    file_content_digest,
    certified_bundle_ids,
)

LABTRUST_RELEASE_REL = Path("examples/pcs_qc_release/release")
PCS_CORE_RC_REL = Path("examples/labtrust-release")

SYNC_ARTIFACTS: tuple[str, ...] = HANDOFF_ARTIFACTS + DOWNSTREAM_ARTIFACTS + (
    RELEASE_FIXTURE_MANIFEST_NAME,
)


def pcs_core_labtrust_release_dir(labtrust_root: Path | None = None) -> Path:
    root = labtrust_root or get_repo_root()
    canonical = resolve_pcs_core_root(root) / PCS_CORE_RC_REL
    if not canonical.is_dir():
        raise FileNotFoundError(
            f"canonical release fixtures not found: {canonical} "
            "(run pcs-core generate-labtrust-release-fixtures or set PCS_CORE_PATH)"
        )
    return canonical


def labtrust_release_dir(labtrust_root: Path | None = None) -> Path:
    return (labtrust_root or get_repo_root()) / LABTRUST_RELEASE_REL


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_hash(release_root: Path, manifest: dict[str, Any], fixture: dict[str, Any], name: str) -> str:
    artifacts = manifest.get("artifacts") or fixture.get("artifacts") or {}
    if name in artifacts:
        return artifacts[name]
    path = release_root / name
    if path.is_file():
        return file_content_digest(path)
    raise FileNotFoundError(f"missing artifact for hash: {name}")


def extract_rc_chain_identity(release_root: Path) -> dict[str, str]:
    """Key fields that must match across repos for the v0.1 RC chain."""
    fixture_manifest_path = release_root / RELEASE_FIXTURE_MANIFEST_NAME
    fixture = _load(fixture_manifest_path) if fixture_manifest_path.is_file() else {}

    manifest_path = release_root / "manifest.json"
    manifest = _load(manifest_path) if manifest_path.is_file() else {}

    certificate = _load(release_root / "trace_certificate.json")
    certified = _load(release_root / "science_claim_bundle.certified.json")
    _, cert_id, trace_hash = certified_bundle_ids(certified)

    return {
        "trace_hash": trace_hash,
        "certificate_id": cert_id,
        "certified_bundle_hash": _artifact_hash(
            release_root, manifest, fixture, "science_claim_bundle.certified.json"
        ),
        "runtime_receipt_hash": _artifact_hash(release_root, manifest, fixture, "runtime_receipt.json"),
        "pending_bundle_hash": _artifact_hash(
            release_root, manifest, fixture, "science_claim_bundle.pending.json"
        ),
        "labtrust_gym_commit": manifest.get("labtrust_gym_commit")
        or fixture.get("labtrust_gym_commit")
        or certified["source_commit"],
        "certifyedge_commit": manifest.get("certifyedge_commit")
        or fixture.get("certifyedge_commit")
        or certificate["source_commit"],
        "provability_fabric_commit": manifest.get("provability_fabric_commit")
        or fixture.get("provability_fabric_commit", ""),
        "scientific_memory_commit": manifest.get("scientific_memory_commit")
        or fixture.get("scientific_memory_commit", ""),
        "pcs_core_commit": manifest.get("pcs_core_commit") or fixture.get("pcs_core_commit", ""),
    }


RC_HANDOFF_COMPARE_KEYS: tuple[str, ...] = (
    "trace_hash",
    "certificate_id",
    "certified_bundle_hash",
    "runtime_receipt_hash",
    "pending_bundle_hash",
    "labtrust_gym_commit",
    "certifyedge_commit",
    "pcs_core_commit",
)


def compare_release_to_pcs_core_rc(
    labtrust_release: Path,
    canonical: Path,
) -> list[str]:
    """Compare canonical RC identity fields; return labels that matched."""
    local_id = extract_rc_chain_identity(labtrust_release.resolve())
    canon_id = extract_rc_chain_identity(canonical.resolve())
    matched: list[str] = []
    for key in RC_HANDOFF_COMPARE_KEYS:
        if local_id.get(key) != canon_id.get(key):
            raise ValueError(
                f"{key} mismatch: local={local_id.get(key)!r} canonical={canon_id.get(key)!r}"
            )
        matched.append(key)
    return matched


def assert_release_matches_pcs_core_rc(
    labtrust_release: Path | None = None,
    canonical: Path | None = None,
) -> dict[str, str]:
    """Raise if LabTrust ``release/`` diverges from pcs-core canonical RC fixtures."""
    lt_root = get_repo_root()
    local = (labtrust_release or labtrust_release_dir(lt_root)).resolve()
    canon = (canonical or pcs_core_labtrust_release_dir(lt_root)).resolve()

    local_id = extract_rc_chain_identity(local)
    canon_id = extract_rc_chain_identity(canon)

    compare_release_to_pcs_core_rc(local, canon)

    for name in HANDOFF_ARTIFACTS:
        local_path = local / name
        canon_path = canon / name
        if not canon_path.is_file():
            raise FileNotFoundError(f"canonical missing {name}")
        if file_content_digest(local_path) != file_content_digest(canon_path):
            raise ValueError(f"artifact bytes mismatch for {name}")

    return local_id


def sync_release_from_pcs_core_rc(
    *,
    labtrust_root: Path | None = None,
    canonical: Path | None = None,
    generator: str = "sync_release_from_pcs_core_rc",
) -> Path:
    """
    Atomically replace LabTrust ``release/`` handoff + flat artifacts from pcs-core canonical dir.

    Rebuilds ``manifest.json``, ``pf_handoff.json``, and ``handoff/`` metadata from synced bytes.
    """
    from labtrust_gym.pcs.release_fixtures import write_trace_hash_alignment

    lt_root = labtrust_root or get_repo_root()
    local = labtrust_release_dir(lt_root)
    canon = canonical or pcs_core_labtrust_release_dir(lt_root)

    staging = local.parent / ".release-sync-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    handoff_staging = staging / "handoff"
    handoff_staging.mkdir()

    for name in SYNC_ARTIFACTS:
        src = canon / name
        if src.is_file():
            shutil.copy2(src, staging / name)

    for name in HANDOFF_ARTIFACTS:
        shutil.copy2(canon / name, handoff_staging / name)

    fixture = _load(staging / RELEASE_FIXTURE_MANIFEST_NAME)
    commits = {
        "labtrust_gym_commit": fixture["labtrust_gym_commit"],
        "certifyedge_commit": fixture["certifyedge_commit"],
        "pcs_core_commit": fixture["pcs_core_commit"],
    }
    if fixture.get("provability_fabric_commit"):
        commits["provability_fabric_commit"] = fixture["provability_fabric_commit"]
    if fixture.get("scientific_memory_commit"):
        commits["scientific_memory_commit"] = fixture["scientific_memory_commit"]

    handoff_manifest = build_handoff_manifest(
        staging,
        commits,
        generator=generator,
        handoff_id=f"labtrust-qc-release-v0.1-{commits['labtrust_gym_commit'][:12]}",
    )
    handoff_manifest["generated_at"] = fixture.get("generated_at", handoff_manifest.get("generated_at"))

    (handoff_staging / RELEASE_HANDOFF_MANIFEST_NAME).write_text(
        json.dumps(handoff_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (handoff_staging / HANDOFF_FOR_PF_NAME).write_text(
        json.dumps(build_handoff_for_pf(staging), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    build_canonical_release_manifest(
        staging,
        handoff_manifest,
        generator=generator,
        certifyedge_bin="certifyedge",
        certifyedge_spec="CertifyEdge/templates/hospital_lab/qc_release.stl",
    )
    build_pf_handoff(staging, _load(staging / "manifest.json"))
    write_trace_hash_alignment(staging)

    if local.exists():
        shutil.rmtree(local)
    shutil.move(str(staging), str(local))

    assert_release_matches_pcs_core_rc(local, canon)
    verify_release_handoff(local)
    return local
