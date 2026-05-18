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
from labtrust_gym.pcs.sync_pcs_core_rc import (
    resolve_canonical_release_dir,
    verify_release_sync_gate,
)


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
) -> list[str]:
    """
    Full Phase 2 protocol verification for ``release/``.

    When ``pcs_core`` is set, also runs the pcs-core RC sync gate.
    """
    release_dir = release_dir.resolve()
    checks: list[str] = []
    checks.extend(assert_release_phase2_protocol_artifacts(release_dir))
    checks.extend(assert_handoff_digests_not_stale(release_dir))
    checks.extend(assert_component_release_fragment_pcs_core(release_dir))

    if pcs_core is not None:
        canonical = resolve_canonical_release_dir(pcs_core, policy_root=policy_root)
        checks.extend(verify_release_sync_gate(release_dir, canonical))
    return checks
