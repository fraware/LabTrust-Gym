"""
Smoke test: after build_viewer_data_from_release, viewer-data/latest/latest.json exists,
referenced bundle file exists, and bundle validates (schema + crosswalk).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_viewer_data_latest_structure_when_present() -> None:
    """When viewer-data/latest/latest.json exists (e.g. after build step in CI), bundle is present."""
    root = _repo_root()
    latest_dir = root / "viewer-data" / "latest"
    latest_json = latest_dir / "latest.json"
    if not latest_json.exists():
        pytest.skip("viewer-data/latest/latest.json not found (run build_viewer_data_from_release first or in CI)")
    assert latest_dir.exists(), "viewer-data/latest dir missing"
    data = json.loads(latest_json.read_text(encoding="utf-8"))
    bundle_file = data.get("bundle_file") or "RISK_REGISTER_BUNDLE.v0.1.json"
    bundle_path = latest_dir / bundle_file
    assert bundle_path.exists(), f"referenced bundle {bundle_file} missing in viewer-data/latest"


def test_viewer_data_bundle_validates_schema_and_crosswalk() -> None:
    """If viewer-data/latest/RISK_REGISTER_BUNDLE.v0.1.json exists, it validates."""
    root = _repo_root()
    bundle_path = root / "viewer-data" / "latest" / "RISK_REGISTER_BUNDLE.v0.1.json"
    if not bundle_path.exists():
        pytest.skip(
            "viewer-data/latest/RISK_REGISTER_BUNDLE.v0.1.json not found (run build_viewer_data_from_release first)"
        )
    from labtrust_gym.export.risk_register_bundle import (
        check_crosswalk_integrity,
        validate_bundle_against_schema,
    )

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    err = validate_bundle_against_schema(bundle, root)
    assert not err, f"schema validation: {err}"
    err2 = check_crosswalk_integrity(bundle)
    assert not err2, f"crosswalk: {err2}"
