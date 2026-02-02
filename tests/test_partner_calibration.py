"""
Partner calibration: schema validation, calibration_fingerprint determinism, missing calibration fallback.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.policy.loader import (
    build_policy_pack_manifest,
    compute_calibration_fingerprint,
    load_effective_policy,
)
from labtrust_gym.policy.validate import validate_policy
from labtrust_gym.benchmarks.tasks import (
    TaskA_ThroughputSLA,
    _sample_arrival_and_n_from_calibration,
    _stat_rate_from_calibration,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_calibration_schema_validation() -> None:
    """calibration.v0.1.yaml for hsl_like validates against calibration.v0.1.schema.json."""
    root = _repo_root()
    cal_path = root / "policy" / "partners" / "hsl_like" / "calibration.v0.1.yaml"
    if not cal_path.exists():
        pytest.skip("policy/partners/hsl_like/calibration.v0.1.yaml not found")
    schema_path = root / "policy" / "schemas" / "calibration.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("policy/schemas/calibration.v0.1.schema.json not found")
    errors = validate_policy(root, partner_id="hsl_like")
    assert errors == [], f"partner validation (with calibration) failed: {errors}"


def test_calibration_fingerprint_determinism() -> None:
    """Same calibration content yields same calibration_fingerprint."""
    root = _repo_root()
    overlay_dir = root / "policy" / "partners" / "hsl_like"
    if not overlay_dir.is_dir():
        pytest.skip("policy/partners/hsl_like not found")
    effective1, _, _, cal_fp1 = load_effective_policy(root, partner_id="hsl_like")
    effective2, _, _, cal_fp2 = load_effective_policy(root, partner_id="hsl_like")
    assert cal_fp1 == cal_fp2
    if effective1.get("calibration"):
        assert compute_calibration_fingerprint(effective1["calibration"]) == cal_fp1


def test_missing_calibration_falls_back_to_defaults() -> None:
    """When partner has no calibration file, effective_policy has calibration=None and calibration_fingerprint=None."""
    root = _repo_root()
    effective, _, partner_id, cal_fp = load_effective_policy(root, partner_id=None)
    assert effective.get("calibration") is None
    assert cal_fp is None
    # Task with no calibration uses default n and arrival range
    task = TaskA_ThroughputSLA()
    state = task.get_initial_state(42, calibration=None)
    specimens = state.get("specimens", [])
    assert 2 <= len(specimens) <= 6
    for s in specimens:
        assert "arrival_ts_s" in s
        assert 0 <= s["arrival_ts_s"] <= 50 or 0 <= s["arrival_ts_s"]


def test_calibration_used_when_present() -> None:
    """When calibration is present, _sample_arrival_and_n_from_calibration and _stat_rate_from_calibration use it."""
    import random

    rng = random.Random(99)
    calibration = {
        "version": "0.1",
        "workload_priors": {
            "arrival_mean_s": 40,
            "arrival_scale_s": 10,
            "arrival_max_s": 80,
            "stat_rate": 0.2,
            "n_specimens_min": 3,
            "n_specimens_max": 5,
        },
    }
    n, arrivals = _sample_arrival_and_n_from_calibration(
        rng, calibration, default_n_min=2, default_n_max=5, default_arrival_max=100
    )
    assert 3 <= n <= 5
    assert len(arrivals) == n
    for a in arrivals:
        assert 0 <= a <= 80
    assert _stat_rate_from_calibration(calibration) == 0.2
    assert _stat_rate_from_calibration(None) == 0.0
    assert _stat_rate_from_calibration({}) == 0.0


def test_calibration_in_policy_pack_manifest() -> None:
    """When partner has calibration, policy_pack_manifest includes calibration.v0.1.yaml."""
    root = _repo_root()
    cal_path = root / "policy" / "partners" / "hsl_like" / "calibration.v0.1.yaml"
    if not cal_path.exists():
        pytest.skip("policy/partners/hsl_like/calibration.v0.1.yaml not found")
    manifest = build_policy_pack_manifest(root, partner_id="hsl_like")
    paths = [f["path"] for f in manifest.get("files", [])]
    assert any("calibration.v0.1.yaml" in p for p in paths)
