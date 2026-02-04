"""
Determinism tests for coordination scale generator.

Same seed + same CoordinationScaleConfig must yield identical:
- agent IDs and order
- device IDs and placement
- site IDs
- initial specimen list (IDs and counts)
- derived placements (zone_layout device_placement, effective_policy)
"""

from pathlib import Path

import pytest

from labtrust_gym.benchmarks.coordination_scale import (
    CoordinationScaleConfig,
    generate_scaled_initial_state,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _small_scale_config() -> CoordinationScaleConfig:
    return CoordinationScaleConfig(
        num_agents_total=10,
        role_mix={
            "ROLE_RUNNER": 0.4,
            "ROLE_ANALYTICS": 0.3,
            "ROLE_RECEPTION": 0.2,
            "ROLE_QC": 0.05,
            "ROLE_SUPERVISOR": 0.05,
        },
        num_devices_per_type={"CHEM_ANALYZER": 2, "CENTRIFUGE_BANK": 1},
        num_sites=1,
        specimens_per_min=2.0,
        horizon_steps=200,
        timing_mode="explicit",
        partner_id=None,
    )


def test_same_seed_same_config_identical_agent_ids() -> None:
    """Same seed and config => identical agent IDs and order."""
    root = _repo_root()
    scale = _small_scale_config()
    s1 = generate_scaled_initial_state(scale, root, 42)
    s2 = generate_scaled_initial_state(scale, root, 42)
    agents1 = [a["agent_id"] for a in s1["agents"]]
    agents2 = [a["agent_id"] for a in s2["agents"]]
    assert agents1 == agents2
    assert agents1 == [f"A_WORKER_{i + 1:04d}" for i in range(10)]


def test_same_seed_same_config_identical_device_ids() -> None:
    """Same seed and config => identical device IDs and placement."""
    root = _repo_root()
    scale = _small_scale_config()
    s1 = generate_scaled_initial_state(scale, root, 42)
    s2 = generate_scaled_initial_state(scale, root, 42)
    dev1 = s1.get("_scale_device_ids") or []
    dev2 = s2.get("_scale_device_ids") or []
    assert dev1 == dev2
    placement1 = (
        (s1.get("effective_policy") or {})
        .get("equipment_registry", {})
        .get("device_instances", [])
    )
    placement2 = (
        (s2.get("effective_policy") or {})
        .get("equipment_registry", {})
        .get("device_instances", [])
    )
    assert [p["device_id"] for p in placement1] == [p["device_id"] for p in placement2]


def test_same_seed_same_config_identical_site_ids() -> None:
    """Same seed and config => identical site IDs in sites_policy."""
    root = _repo_root()
    scale = _small_scale_config()
    s1 = generate_scaled_initial_state(scale, root, 42)
    s2 = generate_scaled_initial_state(scale, root, 42)
    sites1 = (s1.get("effective_policy") or {}).get("sites_policy", {}).get("sites", [])
    sites2 = (s2.get("effective_policy") or {}).get("sites_policy", {}).get("sites", [])
    ids1 = [x["site_id"] for x in sites1]
    ids2 = [x["site_id"] for x in sites2]
    assert ids1 == ids2
    assert ids1 == ["SITE_001"]


def test_same_seed_same_config_identical_initial_specimens() -> None:
    """Same seed and config => identical initial specimen list (IDs and length)."""
    root = _repo_root()
    scale = _small_scale_config()
    s1 = generate_scaled_initial_state(scale, root, 42)
    s2 = generate_scaled_initial_state(scale, root, 42)
    spec1 = s1.get("specimens") or []
    spec2 = s2.get("specimens") or []
    assert len(spec1) == len(spec2)
    ids1 = [x["specimen_id"] for x in spec1]
    ids2 = [x["specimen_id"] for x in spec2]
    assert ids1 == ids2


def test_same_seed_same_config_identical_derived_placements() -> None:
    """Same seed and config => identical zone_layout device_placement."""
    root = _repo_root()
    scale = _small_scale_config()
    s1 = generate_scaled_initial_state(scale, root, 42)
    s2 = generate_scaled_initial_state(scale, root, 42)
    layout1 = (s1.get("effective_policy") or {}).get("zone_layout") or {}
    layout2 = (s2.get("effective_policy") or {}).get("zone_layout") or {}
    dp1 = layout1.get("device_placement") or []
    dp2 = layout2.get("device_placement") or []
    assert len(dp1) == len(dp2)
    for a, b in zip(dp1, dp2):
        assert a.get("device_id") == b.get("device_id")
        assert a.get("zone_id") == b.get("zone_id")


def test_different_seed_different_specimens() -> None:
    """Different seed => different specimen IDs (deterministic but not identical)."""
    root = _repo_root()
    scale = _small_scale_config()
    s1 = generate_scaled_initial_state(scale, root, 42)
    s2 = generate_scaled_initial_state(scale, root, 43)
    ids1 = [x["specimen_id"] for x in (s1.get("specimens") or [])]
    ids2 = [x["specimen_id"] for x in (s2.get("specimens") or [])]
    assert ids1 != ids2 or (len(ids1) == 0 and len(ids2) == 0)


def test_scale_config_sanitized_present() -> None:
    """Generated state includes _scale_config_sanitized for COORD_SCALE_CONFIG emit."""
    root = _repo_root()
    scale = _small_scale_config()
    s = generate_scaled_initial_state(scale, root, 42)
    sanitized = s.get("_scale_config_sanitized")
    assert sanitized is not None
    assert sanitized.get("num_agents_total") == 10
    assert sanitized.get("num_sites") == 1
    assert "role_mix" in sanitized
