#!/usr/bin/env python3
"""CI: validate WorkflowProfile.v0 for QC release reference workflow."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.hash import pcs_digest
from labtrust_gym.pcs.workflow_profile import (
    assert_workflow_profile_valid,
    default_workflow_profile_path,
    load_workflow_profile,
    workflow_profile_view,
)


def main() -> int:
    path = default_workflow_profile_path(ROOT)
    if not path.is_file():
        raise FileNotFoundError(f"missing WorkflowProfile: {path}")

    doc = load_workflow_profile(path, policy_root=ROOT)
    assert_workflow_profile_valid(doc)
    print("OK pcs validate WorkflowProfile.v0", path.name)

    body = {k: v for k, v in doc.items() if k != "signature_or_digest"}
    if doc["signature_or_digest"] != pcs_digest(body):
        raise ValueError("workflow_profile.v0.json signature_or_digest is stale; recompute with pcs_digest")

    subprocess.run(
        ["pcs", "registry", "check-artifact", str(path)],
        check=True,
        cwd=ROOT,
    )
    print("OK pcs registry check-artifact", path.name)

    profile = workflow_profile_view(path, policy_root=ROOT)
    if not profile.requires_runtime_to_certificate or not profile.requires_bundle_to_verifier:
        raise ValueError("QC release profile must require runtime_to_certificate and bundle_to_verifier")
    if len(profile.failure_modes) < 12:
        raise ValueError(f"expected >= 12 failure_modes, got {len(profile.failure_modes)}")
    assert profile.document.get("formalization", {}).get("formalization_scope") == "trust_envelope_only"

    print("OK workflow_id", profile.workflow_id)
    print("OK property_id", profile.property_id)
    print("WorkflowProfile CI OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
