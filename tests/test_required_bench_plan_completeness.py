"""
Gate test: every required_bench cell from method_risk_matrix has a mapping in
required_bench_plan.v0.1.yaml; plan entries reference only implemented method_id,
injection_id (or attack_id), and supported tasks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from labtrust_gym.policy.coordination import get_required_bench_cells, load_method_risk_matrix
from labtrust_gym.security.risk_injections import INJECTION_REGISTRY


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_required_bench_plan_has_entry_for_every_required_cell() -> None:
    """Every (method_id, risk_id) with required_bench true appears in the plan."""
    root = _repo_root()
    matrix_path = root / "policy" / "coordination" / "method_risk_matrix.v0.1.yaml"
    plan_path = root / "policy" / "risks" / "required_bench_plan.v0.1.yaml"
    if not matrix_path.exists() or not plan_path.exists():
        pytest.skip("method_risk_matrix or required_bench_plan not found")
    matrix = load_method_risk_matrix(matrix_path)
    required = get_required_bench_cells(matrix)
    required_keys = {(c["method_id"], c["risk_id"]) for c in required}
    plan_data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    plan_cells = plan_data.get("cells") or []
    plan_keys = {(c["method_id"], c["risk_id"]) for c in plan_cells if isinstance(c, dict)}
    missing = required_keys - plan_keys
    assert not missing, f"required_bench cells without plan entry: {sorted(missing)}"


def test_plan_entries_reference_implemented_injection_ids() -> None:
    """Each plan cell with evidence.kind=coord_risk has injection_id in INJECTION_REGISTRY."""
    root = _repo_root()
    plan_path = root / "policy" / "risks" / "required_bench_plan.v0.1.yaml"
    if not plan_path.exists():
        pytest.skip("required_bench_plan not found")
    plan_data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    for c in plan_data.get("cells") or []:
        if not isinstance(c, dict):
            continue
        ev = c.get("evidence") or {}
        if ev.get("kind") != "coord_risk":
            if ev.get("kind") == "security_suite":
                continue
            pytest.fail(f"unknown evidence.kind: {ev.get('kind')}")
        inj = ev.get("injection_id")
        assert inj, f"coord_risk cell {c.get('method_id')}/{c.get('risk_id')} missing injection_id"
        assert inj in INJECTION_REGISTRY, (
            f"injection_id {inj!r} not in INJECTION_REGISTRY (cell {c.get('method_id')}/{c.get('risk_id')})"
        )


def test_plan_entries_reference_supported_task() -> None:
    """Evidence cmd or task is coord_risk or security_suite (supported)."""
    root = _repo_root()
    plan_path = root / "policy" / "risks" / "required_bench_plan.v0.1.yaml"
    if not plan_path.exists():
        pytest.skip("required_bench_plan not found")
    plan_data = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    supported_tasks = {"coord_risk", "security_suite"}
    for c in plan_data.get("cells") or []:
        if not isinstance(c, dict):
            continue
        ev = c.get("evidence") or {}
        kind = ev.get("kind")
        assert kind in supported_tasks, f"evidence.kind {kind!r} not in {supported_tasks}"
        cmd = ev.get("cmd") or ""
        if kind == "coord_risk" and cmd:
            assert "coord_risk" in cmd or "run-benchmark" in cmd, f"coord_risk cell cmd should run coord_risk: {cmd[:80]}"
        if kind == "security_suite" and cmd:
            assert "security" in cmd or "run-security" in cmd, f"security_suite cell cmd should run security: {cmd[:80]}"
