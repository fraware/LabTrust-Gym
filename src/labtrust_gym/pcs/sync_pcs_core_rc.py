"""Sync LabTrust ``release/`` fixtures from canonical ``pcs-core/examples/labtrust-release/``."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Iterator

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import DETERMINISTIC_CERT_DIGEST, DETERMINISTIC_CERTIFICATE_ID
from labtrust_gym.pcs.manifest import PLACEHOLDER_COMMITS, resolve_pcs_core_root
from labtrust_gym.pcs.mock_certificate import is_mock_certificate
from labtrust_gym.pcs.provenance import LOCAL_DEV_COMMIT
from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_PF_NAME
from labtrust_gym.pcs.release_fragment import LABTRUST_RELEASE_FRAGMENT_NAME
from labtrust_gym.pcs.release_protocol import assert_release_phase2_protocol_artifacts
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
        "trace_json_hash": _artifact_hash(release_root, manifest, fixture, "trace.json"),
        "trace_certificate_hash": _artifact_hash(release_root, manifest, fixture, "trace_certificate.json"),
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
    "trace_json_hash",
    "runtime_receipt_hash",
    "trace_certificate_hash",
    "pending_bundle_hash",
    "certified_bundle_hash",
    "certificate_id",
    "trace_hash",
    "labtrust_gym_commit",
    "certifyedge_commit",
    "pcs_core_commit",
)


def compare_release_to_pcs_core_rc(
    labtrust_release: Path,
    canonical: Path,
) -> list[str]:
    """Compare LabTrust release/ to pcs-core canonical RC by hashes and commits."""
    local = labtrust_release.resolve()
    canon = canonical.resolve()
    local_id = extract_rc_chain_identity(local)
    canon_id = extract_rc_chain_identity(canon)
    matched: list[str] = []
    for key in RC_HANDOFF_COMPARE_KEYS:
        if local_id.get(key) != canon_id.get(key):
            raise ValueError(
                f"{key} mismatch: local={local_id.get(key)!r} canonical={canon_id.get(key)!r}"
            )
        matched.append(key)

    for name in HANDOFF_ARTIFACTS:
        if not (canon / name).is_file():
            raise FileNotFoundError(f"canonical missing {name}")
        local_digest = file_content_digest(local / name)
        canon_digest = file_content_digest(canon / name)
        if local_digest != canon_digest:
            raise ValueError(
                f"{name} hash mismatch: local={local_digest} canonical={canon_digest}"
            )
        matched.append(f"{name}")

    return matched


def _iter_source_commits(obj: Any, *, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else key
            if key == "source_commit" and isinstance(value, str):
                yield child, value
            else:
                yield from _iter_source_commits(value, path=child)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _iter_source_commits(item, path=f"{path}[{i}]")


def _release_scan_json_paths(release_root: Path) -> tuple[str, ...]:
    return HANDOFF_ARTIFACTS + (
        HANDOFF_TO_PF_NAME,
        LABTRUST_RELEASE_FRAGMENT_NAME,
        "verification_result.json",
        "signed_science_claim_bundle.json",
        "scientific_memory_import_report.json",
    )


def assert_release_not_using_mock_certificate(release_root: Path) -> None:
    """Release ``trace_certificate.json`` and embedded certs must not use LabTrust mock IDs."""
    release_root = release_root.resolve()
    cert = _load(release_root / "trace_certificate.json")
    if is_mock_certificate(cert):
        raise ValueError("release/trace_certificate.json must not use LabTrust mock digest")
    if cert.get("certificate_id") == DETERMINISTIC_CERTIFICATE_ID:
        raise ValueError("release/trace_certificate.json must not use mock certificate_id")

    certified = _load(release_root / "science_claim_bundle.certified.json")
    for i, embedded in enumerate(certified.get("certificates", [])):
        if is_mock_certificate(embedded):
            raise ValueError(f"certified.certificates[{i}] must not be mock certificate")
        if embedded.get("certificate_id") == DETERMINISTIC_CERTIFICATE_ID:
            raise ValueError(f"certified.certificates[{i}] must not use mock certificate_id")


def assert_release_not_using_deterministic_cert_digest(release_root: Path) -> None:
    """Release certificate digests must not be the LabTrust deterministic mock value."""
    release_root = release_root.resolve()
    cert = _load(release_root / "trace_certificate.json")
    if cert.get("signature_or_digest") == DETERMINISTIC_CERT_DIGEST:
        raise ValueError("release/trace_certificate.json: deterministic mock digest")

    certified = _load(release_root / "science_claim_bundle.certified.json")
    for i, embedded in enumerate(certified.get("certificates", [])):
        if embedded.get("signature_or_digest") == DETERMINISTIC_CERT_DIGEST:
            raise ValueError(f"certified.certificates[{i}]: deterministic mock digest")


def assert_release_not_using_placeholder_commits(release_root: Path) -> None:
    """Release artifacts must not use golden-only or local-dev placeholder source_commit values."""
    release_root = release_root.resolve()
    for name in _release_scan_json_paths(release_root):
        path = release_root / name
        if not path.is_file():
            continue
        doc = _load(path)
        for field_path, commit in _iter_source_commits(doc):
            if commit in PLACEHOLDER_COMMITS:
                raise ValueError(f"{name} {field_path}: placeholder source_commit {commit!r}")


def assert_release_not_using_local_dev(release_root: Path) -> None:
    """Release evidence must not mark local_dev or use the local-dev source_commit sentinel."""
    release_root = release_root.resolve()
    for name in _release_scan_json_paths(release_root):
        path = release_root / name
        if not path.is_file():
            continue
        doc = _load(path)
        for field_path, commit in _iter_source_commits(doc):
            if commit == LOCAL_DEV_COMMIT:
                raise ValueError(f"{name} {field_path}: local-dev source_commit")
        _assert_no_local_dev_flag(doc, name)


def _assert_no_local_dev_flag(obj: Any, artifact_name: str, *, path: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else key
            if key == "local_dev" and value is True:
                raise ValueError(f"{artifact_name} {child}: local_dev must not be true in release/")
            _assert_no_local_dev_flag(value, artifact_name, path=child)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _assert_no_local_dev_flag(item, artifact_name, path=f"{path}[{i}]")


def assert_release_not_using_mock_or_placeholder(release_root: Path) -> None:
    """Release evidence must not contain mock certificates, placeholders, or local-dev markers."""
    assert_release_not_using_mock_certificate(release_root)
    assert_release_not_using_deterministic_cert_digest(release_root)
    assert_release_not_using_placeholder_commits(release_root)
    assert_release_not_using_local_dev(release_root)


def assert_manifest_matches_pcs_core_fixture_manifest(
    labtrust_release: Path,
    canonical: Path,
) -> list[str]:
    """``release/manifest.json`` handoff artifact digests match pcs-core RELEASE_FIXTURE_MANIFEST."""
    local_manifest = _load(labtrust_release / "manifest.json")
    canon_fixture = _load(canonical / RELEASE_FIXTURE_MANIFEST_NAME)
    matched: list[str] = []
    local_artifacts = local_manifest.get("artifacts") or {}
    canon_artifacts = canon_fixture.get("artifacts") or {}
    for name in HANDOFF_ARTIFACTS:
        if local_artifacts.get(name) != canon_artifacts.get(name):
            raise ValueError(
                f"manifest.artifacts[{name}] != pcs-core RELEASE_FIXTURE_MANIFEST: "
                f"local={local_artifacts.get(name)!r} canonical={canon_artifacts.get(name)!r}"
            )
        matched.append(f"manifest.{name}")
    for key in (
        "labtrust_gym_commit",
        "certifyedge_commit",
        "pcs_core_commit",
    ):
        local_val = local_manifest.get(key)
        canon_val = canon_fixture.get(key)
        if local_val != canon_val:
            raise ValueError(f"manifest.{key} != pcs-core fixture: {local_val!r} != {canon_val!r}")
        matched.append(f"manifest.{key}")
    return matched


def verify_release_sync_gate(
    labtrust_release: Path,
    canonical: Path | None = None,
) -> list[str]:
    """
    Full RC sync gate: local handoff integrity plus optional pcs-core canonical compare.

    When ``canonical`` is set, every handoff artifact must be byte-identical or share the
    same canonical SHA-256 as recorded in both manifests.
    """
    from labtrust_gym.pcs.release_handoff import assert_pf_handoff_matches_release_manifest

    local = labtrust_release.resolve()
    checks: list[str] = []
    assert_release_not_using_mock_or_placeholder(local)
    checks.append("no_mock_or_placeholder_provenance")

    checks.extend(assert_release_phase2_protocol_artifacts(local))

    checks.extend(verify_release_handoff(local))
    assert_pf_handoff_matches_release_manifest(local)
    checks.append("handoff_to_pf_matches_manifest")

    if canonical is not None:
        canon = canonical.resolve()
        checks.extend(assert_manifest_matches_pcs_core_fixture_manifest(local, canon))
        checks.extend(compare_release_to_pcs_core_rc(local, canon))

    return checks


def assert_release_matches_pcs_core_rc(
    labtrust_release: Path | None = None,
    canonical: Path | None = None,
) -> dict[str, str]:
    """Raise if LabTrust ``release/`` diverges from pcs-core canonical RC fixtures."""
    lt_root = get_repo_root()
    local = (labtrust_release or labtrust_release_dir(lt_root)).resolve()
    canon = (canonical or pcs_core_labtrust_release_dir(lt_root)).resolve()

    compare_release_to_pcs_core_rc(local, canon)
    return extract_rc_chain_identity(local)


def sync_release_from_pcs_core_rc(
    *,
    labtrust_root: Path | None = None,
    canonical: Path | None = None,
    generator: str = "sync_release_from_pcs_core_rc",
) -> Path:
    """
    Atomically replace LabTrust ``release/`` handoff + flat artifacts from pcs-core canonical dir.

    Rebuilds ``manifest.json``, ``handoff_to_pf.json``, and ``handoff/`` metadata from synced bytes.
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


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python -m labtrust_gym.pcs.sync_pcs_core_rc``."""
    parser = argparse.ArgumentParser(
        description="Sync or verify LabTrust release/ against pcs-core examples/labtrust-release/",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify local release/ against canonical pcs-core RC (no copy)",
    )
    parser.add_argument(
        "--release",
        type=Path,
        default=None,
        help="LabTrust release directory (default: examples/pcs_qc_release/release)",
    )
    parser.add_argument(
        "--pcs-core",
        type=Path,
        default=None,
        help="pcs-core canonical path (default: sibling pcs-core/examples/labtrust-release)",
    )
    parser.add_argument(
        "--labtrust-root",
        type=Path,
        default=None,
        help="LabTrust-Gym repo root (default: auto-detect)",
    )
    args = parser.parse_args(argv)

    lt_root = (args.labtrust_root or get_repo_root()).resolve()
    release = (args.release or labtrust_release_dir(lt_root)).resolve()
    if args.pcs_core is not None:
        canonical = args.pcs_core.resolve()
    else:
        canonical = pcs_core_labtrust_release_dir(lt_root)

    if args.verify_only:
        for label in verify_release_sync_gate(release, canonical):
            print("OK", label)
        print(f"pcs-core RC verify OK ({release})")
        return 0

    target = sync_release_from_pcs_core_rc(
        labtrust_root=lt_root,
        canonical=canonical,
        generator="labtrust_gym.pcs.sync_pcs_core_rc",
    )
    print(f"OK synced release fixtures -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
