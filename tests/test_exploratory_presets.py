"""Tests for exploratory presets (8.5): exploratory_scale and exploratory_injection."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from labtrust_gym.studies.coordination_security_pack import _resolve_from_preset


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_pack_config() -> dict:
    root = _repo_root()
    path = root / "policy" / "coordination" / "coordination_security_pack.v0.1.yaml"
    if not path.exists():
        pytest.skip("coordination_security_pack.v0.1.yaml not found")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_exploratory_scale_preset_has_extra_scale() -> None:
    """Load preset exploratory_scale; assert it contains exactly one extra scale (exploratory_scale)."""
    root = _repo_root()
    pack_config = _load_pack_config()
    scales, methods, injections = _resolve_from_preset(root, "exploratory_scale", pack_config)
    assert "exploratory_scale" in scales
    assert len(scales) >= 2
    scale_configs_path = root / "policy" / "coordination" / "scale_configs.v0.1.yaml"
    with open(scale_configs_path, encoding="utf-8") as f:
        scale_data = yaml.safe_load(f)
    configs = (scale_data.get("scale_configs") or {}).get("configs") or []
    scale_ids = [c.get("id") for c in configs if c.get("id")]
    assert "exploratory_scale" in scale_ids


def test_exploratory_injection_preset_has_extra_injection() -> None:
    """Load preset exploratory_injection; assert it contains one extra injection (duplicate INJ-COMMS-POISON-001)."""
    root = _repo_root()
    pack_config = _load_pack_config()
    scales, methods, injections = _resolve_from_preset(root, "exploratory_injection", pack_config)
    assert len(injections) >= 3
    assert "none" in injections
    assert "INJ-COMMS-POISON-001" in injections
    assert injections.count("INJ-COMMS-POISON-001") >= 1
