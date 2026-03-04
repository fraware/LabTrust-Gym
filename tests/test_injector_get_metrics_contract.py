"""Tests for injector get_metrics() contract (3a.3): required keys for sec.* aggregation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from labtrust_gym.security.risk_injections import make_injector

_REQUIRED_GET_METRICS_KEYS = (
    "attack_success",
    "first_application_step",
    "first_detection_step",
    "first_containment_step",
)


def _hospital_lab_injection_ids() -> list[str]:
    root = Path(__file__).resolve().parent.parent
    path = root / "policy" / "coordination" / "coordination_security_pack.v0.1.yaml"
    if not path.exists():
        return ["none", "INJ-ID-SPOOF-001", "INJ-COMMS-POISON-001"]
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    presets = data.get("matrix_presets") or {}
    hospital = presets.get("hospital_lab")
    if not isinstance(hospital, dict):
        return ["none", "INJ-ID-SPOOF-001", "INJ-COMMS-POISON-001"]
    ids = hospital.get("injection_ids")
    if isinstance(ids, list):
        return list(ids)
    return ["none", "INJ-ID-SPOOF-001", "INJ-COMMS-POISON-001"]


@pytest.mark.parametrize("injection_id", _hospital_lab_injection_ids())
def test_injector_get_metrics_has_required_keys(injection_id: str) -> None:
    """Each pack injector get_metrics() returns the keys required by compute_episode_metrics."""
    injector = make_injector(injection_id)
    injector.reset(42, None)
    metrics = injector.get_metrics()
    assert isinstance(metrics, dict)
    for key in _REQUIRED_GET_METRICS_KEYS:
        assert key in metrics, f"injection_id={injection_id!r} get_metrics() must include {key!r}"


@pytest.mark.slow
def test_pack_run_cells_have_sec_attack_success_rate(tmp_path: Path) -> None:
    """Run coordination security pack with minimal preset; assert each row has sec.attack_success_rate (3a.3)."""
    from labtrust_gym.studies.coordination_security_pack import run_coordination_security_pack

    root = Path(__file__).resolve().parent.parent
    out_dir = tmp_path / "pack_out"
    run_coordination_security_pack(
        out_dir=out_dir,
        repo_root=root,
        seed_base=42,
        matrix_preset="exploratory_injection",
        workers=1,
    )
    pack_summary = out_dir / "pack_summary.csv"
    assert pack_summary.exists()
    content = pack_summary.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert len(lines) >= 2
    header = lines[0]
    assert "sec.attack_success_rate" in header
    import csv
    from io import StringIO

    reader = csv.DictReader(StringIO(content))
    for row in reader:
        assert "sec.attack_success_rate" in row
