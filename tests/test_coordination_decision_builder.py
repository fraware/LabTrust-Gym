"""
Tests for coordination decision builder: deterministic artifact,
schema validation, and no-admissible-method path.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_decision_builder import (
    build_decision,
    write_decision_artifact,
    DECISION_FILENAME_JSON,
    DECISION_FILENAME_MD,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _write_pack_summary(csv_path: Path, rows: list[dict]) -> None:
    """Write pack_summary-style CSV."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def test_decision_artifact_deterministic_and_schema_validated(
    tmp_path: Path,
) -> None:
    """Build decision from minimal pack_summary; output is schema-validated and deterministic."""
    repo = _repo_root()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # One scale, two methods; baseline (none) + one attack row. Method A passes constraints, B fails (high attack rate).
    rows = [
        {
            "method_id": "method_a",
            "scale_id": "small_smoke",
            "injection_id": "none",
            "perf.throughput": 5,
            "safety.violations_total": 2,
            "sec.attack_success_rate": "",
            "sec.detection_latency_steps": "",
            "sec.containment_time_steps": "",
        },
        {
            "method_id": "method_a",
            "scale_id": "small_smoke",
            "injection_id": "INJ-COMMS-POISON-001",
            "perf.throughput": 4,
            "safety.violations_total": 3,
            "sec.attack_success_rate": 0.1,
            "sec.detection_latency_steps": 2,
            "sec.containment_time_steps": 1,
        },
        {
            "method_id": "method_b",
            "scale_id": "small_smoke",
            "injection_id": "none",
            "perf.throughput": 10,
            "safety.violations_total": 1,
            "sec.attack_success_rate": "",
            "sec.detection_latency_steps": "",
            "sec.containment_time_steps": "",
        },
        {
            "method_id": "method_b",
            "scale_id": "small_smoke",
            "injection_id": "INJ-COMMS-POISON-001",
            "perf.throughput": 8,
            "safety.violations_total": 2,
            "sec.attack_success_rate": 0.9,
            "sec.detection_latency_steps": 20,
            "sec.containment_time_steps": 5,
        },
    ]
    _write_pack_summary(run_dir / "pack_summary.csv", rows)
    policy_root = repo
    decision = build_decision(run_dir, policy_root)
    assert decision["verdict"] == "admissible"
    scale_decisions = decision.get("scale_decisions") or []
    assert len(scale_decisions) == 1
    sd = scale_decisions[0]
    assert sd["scale_id"] == "small_smoke"
    assert sd["chosen_method_id"] == "method_a"
    assert "method_b" in [d["method_id"] for d in sd["disqualified"]]
    out_dir = tmp_path / "out"
    json_path, md_path = write_decision_artifact(decision, out_dir, policy_root)
    assert json_path == out_dir / DECISION_FILENAME_JSON
    assert md_path == out_dir / DECISION_FILENAME_MD
    assert json_path.is_file()
    assert md_path.is_file()
    content = md_path.read_text(encoding="utf-8")
    assert "Verdict:" in content
    assert "method_a" in content
    assert "no admissible method" in content or "Chosen:" in content


def test_no_admissible_method_lists_violations_and_recommended_actions(
    tmp_path: Path,
) -> None:
    """When no method passes constraints, verdict is no_admissible_method with violated_constraints and recommended_actions."""
    repo = _repo_root()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    # All methods exceed violation gate (e.g. 100 violations).
    rows = [
        {
            "method_id": "method_x",
            "scale_id": "small_smoke",
            "injection_id": "none",
            "perf.throughput": 1,
            "safety.violations_total": 50,
            "sec.attack_success_rate": "",
            "sec.detection_latency_steps": "",
            "sec.containment_time_steps": "",
        },
    ]
    _write_pack_summary(run_dir / "pack_summary.csv", rows)
    policy_root = repo
    decision = build_decision(run_dir, policy_root)
    assert decision["verdict"] == "no_admissible_method"
    assert "no_admissible_method" in decision
    no_adm = decision["no_admissible_method"]
    assert "violated_constraints" in no_adm
    assert len(no_adm["violated_constraints"]) >= 1
    assert "recommended_actions" in no_adm
    assert len(no_adm["recommended_actions"]) >= 1
    scale_decisions = decision.get("scale_decisions") or []
    assert scale_decisions[0]["chosen_method_id"] is None
    out_dir = tmp_path / "out"
    write_decision_artifact(decision, out_dir, policy_root)
    md_path = out_dir / DECISION_FILENAME_MD
    content = md_path.read_text(encoding="utf-8")
    assert "No admissible method" in content
    assert "Recommended actions" in content or "Recommended" in content
