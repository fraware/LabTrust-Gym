"""Verify LabTrust ``release/`` Phase 2 protocol artifacts (schema, registry, digests)."""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.pcs.release_fragment import (
    LABTRUST_RELEASE_FRAGMENT_NAME,
    assert_release_fragment_registry_check,
    assert_release_fragment_valid,
)
from labtrust_gym.pcs.release_protocol import (
    assert_handoff_digests_not_stale,
    assert_release_phase2_protocol_artifacts,
)
from labtrust_gym.pcs.release_fixtures import RELEASE_ARTIFACTS
from labtrust_gym.pcs.status_policy import assert_release_bundle_status_policy
from labtrust_gym.pcs.protocol_artifacts import WORKFLOW_PROFILE_RELEASE_NAME
from labtrust_gym.pcs.workflow_profile import (
    assert_workflow_profile_valid,
    default_workflow_profile_path,
    load_workflow_profile,
    workflow_profile_view,
)
from labtrust_gym.pcs.sync_pcs_core_rc import (
    assert_release_not_using_mock_or_placeholder,
    resolve_canonical_release_dir,
    verify_release_sync_gate,
)

def assert_release_artifact_schema_validation(release_root: Path) -> list[str]:
    """Validate core release JSON artifacts against pcs-core schemas."""
    from pcs_core.validate import validate_artifact

    from labtrust_gym.pcs.schema_version import assert_no_legacy_pf_bundle_keys
    from labtrust_gym.pcs.validate import (
        require_pcs_core,
        validate_runtime_receipt,
        validate_science_claim_bundle,
        validate_trace,
    )

    require_pcs_core()
    release_root = release_root.resolve()
    checks: list[str] = []

    trace = json.loads((release_root / "trace.json").read_text(encoding="utf-8"))
    receipt = json.loads((release_root / "runtime_receipt.json").read_text(encoding="utf-8"))
    certificate = json.loads((release_root / "trace_certificate.json").read_text(encoding="utf-8"))
    pending = json.loads((release_root / "science_claim_bundle.pending.json").read_text(encoding="utf-8"))
    certified = json.loads((release_root / "science_claim_bundle.certified.json").read_text(encoding="utf-8"))

    validate_trace(trace)
    checks.append("schema_validate_trace")
    validate_runtime_receipt(receipt)
    validate_artifact(receipt)
    checks.append("schema_validate_runtime_receipt")
    validate_artifact(certificate)
    checks.append("schema_validate_trace_certificate")
    validate_science_claim_bundle(pending)
    validate_artifact(pending)
    checks.append("schema_validate_pending_bundle")
    validate_science_claim_bundle(certified)
    validate_artifact(certified)
    checks.append("schema_validate_certified_bundle")
    assert_no_legacy_pf_bundle_keys(pending)
    assert_no_legacy_pf_bundle_keys(certified)
    checks.append("no_legacy_pf_bundle_keys")
    return checks


def assert_component_release_fragment_pcs_core(release_root: Path) -> list[str]:
    """Validate fragment with pcs-core schema and registry."""
    release_root = release_root.resolve()
    fragment_path = release_root / LABTRUST_RELEASE_FRAGMENT_NAME
    if not fragment_path.is_file():
        raise FileNotFoundError(f"missing {LABTRUST_RELEASE_FRAGMENT_NAME}")

    fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
    assert_release_fragment_valid(fragment)
    assert_release_fragment_registry_check(fragment_path)
    return ["component_release_fragment_schema", "component_release_fragment_registry"]


def verify_release_protocol(
    release_dir: Path,
    *,
    pcs_core: Path | None = None,
    policy_root: Path | None = None,
    compare_canonical: bool = True,
) -> list[str]:
    """
    Full Phase 2 protocol verification for ``release/``.

    Runs schema validation, registry checks, handoff digest checks, status-policy
    enforcement, mock-certificate and placeholder-commit rejection, and optional
    pcs-core RC byte alignment when ``pcs_core`` is set and ``compare_canonical`` is
    true (default). Set ``compare_canonical=False`` for freshly regenerated trees
    where live CertifyEdge output must not match pinned fixture bytes.
    """
    release_dir = release_dir.resolve()
    checks: list[str] = []

    profile_path = default_workflow_profile_path(policy_root)
    release_profile_path = release_dir / WORKFLOW_PROFILE_RELEASE_NAME
    if profile_path.is_file():
        profile_doc = load_workflow_profile(profile_path, policy_root=policy_root)
        assert_workflow_profile_valid(profile_doc)
        profile = workflow_profile_view(profile_path, policy_root=policy_root)
        checks.append("workflow_profile_schema")
        if profile.requires_runtime_to_certificate and profile.requires_bundle_to_verifier:
            checks.append("workflow_profile_handoff_sequence")
        if release_profile_path.is_file():
            release_doc = load_workflow_profile(release_profile_path, policy_root=policy_root)
            assert_workflow_profile_valid(release_doc)
            if release_doc.get("workflow_id") != profile.workflow_id:
                raise ValueError(
                    "release workflow_profile workflow_id does not match repo profile"
                )
            if release_doc.get("signature_or_digest") != profile_doc.get("signature_or_digest"):
                raise ValueError(
                    "release workflow_profile digest does not match repo profile; "
                    "re-run regenerate-release-protocol"
                )
            checks.append("release_workflow_profile_pinned")
    else:
        profile = None

    checks.extend(assert_release_phase2_protocol_artifacts(release_dir))
    checks.extend(assert_handoff_digests_not_stale(release_dir))
    checks.extend(assert_component_release_fragment_pcs_core(release_dir))
    checks.extend(assert_release_bundle_status_policy(release_dir, profile=profile))
    checks.append("status_transition_policy")

    assert_release_not_using_mock_or_placeholder(release_dir)
    checks.append("no_mock_certificate")
    checks.append("no_placeholder_commits")
    checks.append("no_local_dev_provenance")

    checks.extend(assert_release_artifact_schema_validation(release_dir))

    # Ensure committed release tree still has the full golden set when present.
    for name in RELEASE_ARTIFACTS:
        if (release_dir / name).is_file():
            checks.append(f"release_artifact_present_{name}")

    if (release_dir / "manifest.json").is_file():
        from labtrust_gym.pcs.release_handoff import verify_release_handoff

        checks.extend(verify_release_handoff(release_dir))

    if (release_dir / "signed_science_claim_bundle.json").is_file():
        from labtrust_gym.pcs.scientific_memory_import import assert_scientific_memory_import_alignment

        assert_scientific_memory_import_alignment(release_dir)
        checks.append("scientific_memory_import_alignment")

    if pcs_core is not None and compare_canonical:
        canonical = resolve_canonical_release_dir(pcs_core, policy_root=policy_root)
        checks.extend(verify_release_sync_gate(release_dir, canonical))

    return checks
