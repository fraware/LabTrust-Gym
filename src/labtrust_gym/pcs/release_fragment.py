"""LabTrust-owned ReleaseManifest fragment for pcs-core aggregation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.handoff_manifest import HANDOFF_TO_PF_NAME
from labtrust_gym.pcs.manifest import PLACEHOLDER_COMMITS, _git_head, resolve_pcs_core_root
from labtrust_gym.pcs.provenance import SOURCE_REPO
from labtrust_gym.pcs.release_provenance import assert_no_placeholder_commits, labtrust_source_commit_paths
from labtrust_gym.pcs.release_run import file_content_digest

LABTRUST_RELEASE_FRAGMENT_NAME = "labtrust_release_fragment.json"
COMPONENT_NAME = "LabTrust-Gym"

LABTRUST_FRAGMENT_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("trace.json", "Trace"),
    ("runtime_receipt.json", "RuntimeReceipt.v0"),
    ("science_claim_bundle.pending.json", "ScienceClaimBundle.v0"),
    ("science_claim_bundle.certified.json", "ScienceClaimBundle.v0"),
    (HANDOFF_TO_PF_NAME, "HandoffManifest.v0"),
)


def release_fragment_schema_paths() -> list[Path]:
    """Prefer pcs-core schema when published; fall back to LabTrust policy copy."""
    paths: list[Path] = []
    try:
        core = resolve_pcs_core_root() / "schemas" / "LabTrustReleaseFragment.v0.schema.json"
        if core.is_file():
            paths.append(core)
    except FileNotFoundError:
        pass
    bundled = get_repo_root() / "policy" / "schemas" / "pcs" / "LabTrustReleaseFragment.v0.schema.json"
    if bundled.is_file():
        paths.append(bundled)
    return paths


def validate_release_fragment(doc: dict[str, Any]) -> list[str]:
    """Validate fragment against pcs-core or bundled JSON Schema."""
    schema_paths = release_fragment_schema_paths()
    if not schema_paths:
        return []
    schema_path = schema_paths[0]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    from pcs_core.validate import get_registry

    validator = Draft202012Validator(schema, registry=get_registry())
    return sorted(e.message for e in validator.iter_errors(doc))


def assert_release_fragment_valid(doc: dict[str, Any]) -> None:
    errors = validate_release_fragment(doc)
    if errors:
        raise ValueError("LabTrustReleaseFragment validation failed: " + "; ".join(errors))


def build_labtrust_release_fragment(
    release_dir: Path,
    *,
    policy_root: Path | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    """Build LabTrust component fragment from ``release/`` directory artifacts."""
    release_dir = release_dir.resolve()
    root = policy_root or get_repo_root()
    commit = source_commit or _git_head(root)
    assert_no_placeholder_commits(commit, context="labtrust_release_fragment")

    artifacts: dict[str, Any] = {}
    for filename, artifact_type in LABTRUST_FRAGMENT_ARTIFACTS:
        path = release_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"release fragment missing artifact: {filename}")
        artifacts[filename] = {
            "artifact_type": artifact_type,
            "sha256": file_content_digest(path),
        }

    doc: dict[str, Any] = {
        "schema_version": "v0",
        "component": COMPONENT_NAME,
        "source_repo": SOURCE_REPO,
        "source_commit": commit,
        "artifacts": artifacts,
    }
    assert_release_fragment_valid(doc)
    return doc


def assert_release_fragment_source_commit_matches_artifacts(
    release_dir: Path,
    fragment: dict[str, Any],
) -> None:
    """Nested LabTrust artifact source_commit values must match fragment.source_commit."""
    release_dir = release_dir.resolve()
    commit = fragment["source_commit"]
    if commit in PLACEHOLDER_COMMITS:
        raise ValueError("fragment source_commit must not be a placeholder")

    for filename in (
        "science_claim_bundle.pending.json",
        "science_claim_bundle.certified.json",
    ):
        bundle = json.loads((release_dir / filename).read_text(encoding="utf-8"))
        for path, sc in labtrust_source_commit_paths(bundle):
            if sc != commit:
                raise ValueError(f"{filename}.{path} source_commit {sc!r} != fragment {commit!r}")


def emit_labtrust_release_fragment(
    *,
    release_dir: Path,
    out_path: Path | None = None,
    policy_root: Path | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    """Write ``labtrust_release_fragment.json`` under ``release_dir``."""
    release_dir = release_dir.resolve()
    manifest_path = release_dir / "manifest.json"
    if source_commit is None and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_commit = manifest.get("labtrust_gym_commit")

    doc = build_labtrust_release_fragment(
        release_dir,
        policy_root=policy_root,
        source_commit=source_commit,
    )
    assert_release_fragment_source_commit_matches_artifacts(release_dir, doc)

    target = out_path or (release_dir / LABTRUST_RELEASE_FRAGMENT_NAME)
    target = target.resolve()
    target.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc
