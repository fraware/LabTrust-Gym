"""
EvidenceBundle manifests from package-release must include all four required fingerprints.
Tests that export_receipts with compute_bundle_fingerprints_required produces manifests
with rbac_policy_fingerprint, tool_registry_fingerprint, coordination_policy_fingerprint,
memory_policy_fingerprint (non-empty).
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.config import get_repo_root
from labtrust_gym.export.receipts import (
    compute_bundle_fingerprints_required,
    export_receipts,
)

REQUIRED_KEYS = [
    "rbac_policy_fingerprint",
    "tool_registry_fingerprint",
    "coordination_policy_fingerprint",
    "memory_policy_fingerprint",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_compute_bundle_fingerprints_required_returns_all_four() -> None:
    """Strict fingerprint helper returns all four keys with non-empty values in repo."""
    root = get_repo_root()
    fps = compute_bundle_fingerprints_required(root)
    for key in REQUIRED_KEYS:
        assert key in fps, f"missing {key}"
        assert isinstance(fps[key], str) and len(fps[key]) > 0, f"empty {key}"


def test_export_receipts_with_required_fingerprints_writes_manifest_with_all_four(
    tmp_path: Path,
) -> None:
    """Export one minimal EvidenceBundle with required fingerprints; manifest has all four keys."""
    root = get_repo_root()
    fingerprints = compute_bundle_fingerprints_required(root)
    # Minimal one-line episode log so export_receipts produces one receipt
    log_path = tmp_path / "episodes.jsonl"
    log_path.write_text(
        '{"t_s":0,"agent_id":"A","action_type":"TICK","status":"ACCEPTED","hashchain":{"head_hash":"","length":0,"last_event_hash":""}}\n',
        encoding="utf-8",
    )
    out_dir = tmp_path / "receipts"
    out_dir.mkdir(parents=True, exist_ok=True)
    export_receipts(
        log_path,
        out_dir,
        policy_root=root,
        tool_registry_fingerprint=fingerprints.get("tool_registry_fingerprint"),
        rbac_policy_fingerprint=fingerprints.get("rbac_policy_fingerprint"),
        coordination_policy_fingerprint=fingerprints.get("coordination_policy_fingerprint"),
        memory_policy_fingerprint=fingerprints.get("memory_policy_fingerprint"),
    )
    bundle_dir = out_dir / "EvidenceBundle.v0.1"
    assert bundle_dir.is_dir(), "EvidenceBundle.v0.1 not created"
    manifest_path = bundle_dir / "manifest.json"
    assert manifest_path.exists(), "manifest.json missing"
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in REQUIRED_KEYS:
        assert key in manifest, f"manifest missing {key}"
        assert isinstance(manifest[key], str) and len(manifest[key]) > 0, f"manifest empty {key}"
