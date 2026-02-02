"""
Tests for partner overlay: load/merge determinism, invalid overlay fails schema,
merged policy used by engine/benchmarks (smoke).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.policy.loader import (
    PolicyLoadError,
    load_effective_policy,
    load_partners_index,
    get_partner_overlay_dir,
    compute_policy_fingerprint,
)
from labtrust_gym.policy.overlay import (
    merge_critical_thresholds,
    merge_stability_policy,
    merge_enforcement_map,
)
from labtrust_gym.policy.validate import (
    validate_policy,
    validate_partner_overlay_files,
    validate_merged_policy_consistency,
)


def _repo_root() -> Path:
    cwd = Path.cwd()
    for p in [cwd, cwd.parent]:
        if (p / "policy" / "partners").is_dir():
            return p
    return cwd


def test_merge_critical_thresholds_determinism() -> None:
    base = [
        {
            "analyte_code": "K",
            "units": "mmol/L",
            "low": 2.5,
            "high": 6.5,
            "class": "CRIT_A",
        },
        {
            "analyte_code": "Na",
            "units": "mmol/L",
            "low": 120,
            "high": 160,
            "class": "CRIT_A",
        },
    ]
    overlay = [
        {
            "analyte_code": "K",
            "units": "mmol/L",
            "low": 2.8,
            "high": 6.0,
            "class": "CRIT_A",
        },
    ]
    merged = merge_critical_thresholds(base, overlay)
    assert len(merged) == 2
    k_entry = next(m for m in merged if m.get("analyte_code") == "K")
    assert k_entry["low"] == 2.8 and k_entry["high"] == 6.0
    na_entry = next(m for m in merged if m.get("analyte_code") == "Na")
    assert na_entry["low"] == 120


def test_merge_stability_policy_panel_override() -> None:
    base = {"policy_version": "0.1", "panel_rules": {"PANEL_A": {"intent": "base"}}}
    overlay = {"panel_rules": {"PANEL_A": {"intent": "overlay"}}}
    merged = merge_stability_policy(base, overlay)
    assert merged["panel_rules"]["PANEL_A"]["intent"] == "overlay"


def test_merge_enforcement_map_rule_override() -> None:
    base = {
        "version": "0.1",
        "rules": [
            {
                "rule_id": "R1",
                "match": {},
                "action": {"type": "throttle_agent", "duration_s": 60},
            }
        ],
    }
    overlay = {
        "rules": [
            {
                "rule_id": "R1",
                "match": {},
                "action": {"type": "throttle_agent", "duration_s": 90},
            }
        ]
    }
    merged = merge_enforcement_map(base, overlay)
    r1 = next(r for r in merged["rules"] if r.get("rule_id") == "R1")
    assert r1["action"]["duration_s"] == 90


def test_load_partners_index() -> None:
    root = _repo_root()
    partners = load_partners_index(root)
    assert isinstance(partners, list)
    hsl = next((p for p in partners if p.get("partner_id") == "hsl_like"), None)
    if hsl:
        assert "description" in hsl or "overlay_path" in hsl


def test_load_effective_policy_base_only() -> None:
    root = _repo_root()
    effective, fingerprint, partner_id, cal_fp = load_effective_policy(
        root, partner_id=None
    )
    assert partner_id is None
    assert cal_fp is None
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert "critical_thresholds" in effective
    assert "stability_policy" in effective
    assert "enforcement_map" in effective
    assert "equipment_registry" in effective
    assert effective.get("calibration") is None


def test_load_effective_policy_with_partner_determinism() -> None:
    root = _repo_root()
    overlay_dir = get_partner_overlay_dir(root, "hsl_like")
    if not overlay_dir.is_dir():
        pytest.skip("policy/partners/hsl_like not present")
    effective1, fp1, _, cal_fp1 = load_effective_policy(root, partner_id="hsl_like")
    effective2, fp2, _, cal_fp2 = load_effective_policy(root, partner_id="hsl_like")
    assert fp1 == fp2
    assert cal_fp1 == cal_fp2
    assert compute_policy_fingerprint(effective1) == fp1
    assert effective1["critical_thresholds"] != [] or "BIOCHEM_POTASSIUM_K" in str(
        effective1
    )


def test_validate_policy_base_and_partner() -> None:
    root = _repo_root()
    errors = validate_policy(root, partner_id=None)
    assert errors == [], f"base validation failed: {errors}"
    errors_partner = validate_policy(root, partner_id="hsl_like")
    assert errors_partner == [], f"base+partner validation failed: {errors_partner}"


def test_invalid_overlay_fails_schema(tmp_path: Path) -> None:
    """Invalid overlay (missing required keys) should fail schema validation."""
    from labtrust_gym.policy.loader import load_yaml, load_json, validate_against_schema

    root = _repo_root()
    bad_overlay = tmp_path / "critical"
    bad_overlay.mkdir()
    (bad_overlay / "critical_thresholds.v0.1.yaml").write_text(
        "critical_thresholds:\n  version: 0.1\n"
    )
    schemas_dir = root / "policy" / "schemas"
    schema = load_json(schemas_dir / "critical_thresholds.v0.1.schema.json")
    data = load_yaml(bad_overlay / "critical_thresholds.v0.1.yaml")
    with pytest.raises(PolicyLoadError):
        validate_against_schema(
            data, schema, bad_overlay / "critical_thresholds.v0.1.yaml"
        )


def test_benchmark_smoke_with_partner() -> None:
    """Run 2 episodes with partner hsl_like; results must include partner_id and policy_fingerprint."""
    root = _repo_root()
    if not (root / "policy" / "partners" / "hsl_like").is_dir():
        pytest.skip("policy/partners/hsl_like not present")
    from labtrust_gym.benchmarks.runner import run_benchmark

    out_path = root / "bench_smoke_partner_test.json"
    try:
        results = run_benchmark(
            task_name="TaskA",
            num_episodes=2,
            base_seed=42,
            out_path=out_path,
            repo_root=root,
            partner_id="hsl_like",
        )
        assert results.get("partner_id") == "hsl_like"
        assert results.get("policy_fingerprint") is not None
        assert (
            isinstance(results["policy_fingerprint"], str)
            and len(results["policy_fingerprint"]) == 64
        )
    finally:
        if out_path.exists():
            out_path.unlink()


def test_same_seed_same_partner_same_output() -> None:
    """Determinism: same seed + same partner => identical policy_fingerprint and same episode metrics."""
    root = _repo_root()
    if not (root / "policy" / "partners" / "hsl_like").is_dir():
        pytest.skip("policy/partners/hsl_like not present")
    from labtrust_gym.benchmarks.runner import run_benchmark

    out1 = root / "bench_det_1.json"
    out2 = root / "bench_det_2.json"
    try:
        r1 = run_benchmark(
            task_name="TaskA",
            num_episodes=1,
            base_seed=99,
            out_path=out1,
            repo_root=root,
            partner_id="hsl_like",
        )
        r2 = run_benchmark(
            task_name="TaskA",
            num_episodes=1,
            base_seed=99,
            out_path=out2,
            repo_root=root,
            partner_id="hsl_like",
        )
        assert r1["policy_fingerprint"] == r2["policy_fingerprint"]
        assert r1["episodes"][0]["metrics"] == r2["episodes"][0]["metrics"]
    finally:
        for p in (out1, out2):
            if p.exists():
                p.unlink()


def test_validate_partner_overlay_files_missing_dir() -> None:
    root = _repo_root()
    errors = validate_partner_overlay_files(root, "nonexistent_partner_xyz")
    assert len(errors) >= 1
    assert "not found" in errors[0].lower() or "nonexistent" in errors[0].lower()


def test_validate_merged_consistency() -> None:
    root = _repo_root()
    errors = validate_merged_policy_consistency(root, partner_id=None)
    assert errors == [], f"merged consistency (base only) failed: {errors}"
    if (root / "policy" / "partners" / "hsl_like").is_dir():
        errors2 = validate_merged_policy_consistency(root, partner_id="hsl_like")
        assert errors2 == [], f"merged consistency (hsl_like) failed: {errors2}"
