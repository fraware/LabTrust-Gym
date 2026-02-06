"""
Coordination Interface Contract v0.1: telemetry schema validation,
coord_decisions.jsonl produced by every registry method, strict mode fails on missing fields.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.telemetry import (
    build_contract_record,
    serialize_contract_record,
    validate_contract_record,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_build_contract_record_validates() -> None:
    """A record built with build_contract_record validates against the schema."""
    record = build_contract_record(
        method_id="centralized_planner",
        t_step=0,
        actions_dict={
            "worker_0": {"action_index": 0},
            "worker_1": {
                "action_index": 3,
                "action_type": "MOVE",
                "args": {"to_zone": "Z_A"},
            },
        },
        view_age_ms=10.5,
        plan_time_ms=None,
        invariants_considered=["INV-COC-001"],
        safety_shield_applied=False,
    )
    schema_path = _repo_root() / "policy" / "schemas"
    schema_path = schema_path / "coord_method_output_contract.v0.1.schema.json"
    errors = validate_contract_record(record, schema_path=schema_path)
    assert not errors, f"Valid record must pass: {errors}"


def test_strict_mode_fails_on_missing_fields() -> None:
    """Validation fails when required fields (method_id, t_step, actions) are missing."""
    schema_path = _repo_root() / "policy" / "schemas"
    schema_path = schema_path / "coord_method_output_contract.v0.1.schema.json"
    if not schema_path.exists():
        pytest.skip("Schema not found")
    missing_method = {"t_step": 0, "actions": []}
    errs = validate_contract_record(missing_method, schema_path=schema_path)
    assert errs, "Missing method_id must fail validation"
    missing_t_step = {"method_id": "x", "actions": []}
    errs = validate_contract_record(missing_t_step, schema_path=schema_path)
    assert errs, "Missing t_step must fail validation"
    missing_actions = {"method_id": "x", "t_step": 0}
    errs = validate_contract_record(missing_actions, schema_path=schema_path)
    assert errs, "Missing actions must fail"


def test_serialize_contract_record_one_line() -> None:
    """Serialized record is one line (JSONL)."""
    record = build_contract_record("kernel_centralized_edf", 1, {"w0": {"action_index": 0}})
    line = serialize_contract_record(record)
    assert "\n" in line
    assert line.count("\n") == 1
    parsed = json.loads(line.strip())
    assert parsed["method_id"] == "kernel_centralized_edf"
    assert parsed["t_step"] == 1


def test_coord_decisions_jsonl_produced_for_taskg() -> None:
    """TaskG with coord method and log_path produces coord_decisions.jsonl."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.benchmarks.runner import run_benchmark

    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        log_path = Path(tmp) / "episodes.jsonl"
        run_benchmark(
            task_name="TaskG_COORD_SCALE",
            num_episodes=1,
            base_seed=42,
            out_path=out,
            repo_root=root,
            log_path=log_path,
            coord_method="centralized_planner",
        )
        coord_decisions = Path(tmp) / "coord_decisions.jsonl"
        assert coord_decisions.exists(), "coord_decisions.jsonl must be produced"
        text = coord_decisions.read_text(encoding="utf-8").strip()
        lines = [ln for ln in text.splitlines() if ln.strip()]
        assert len(lines) >= 1, "At least one step decision"
        schema_path = root / "policy" / "schemas"
        schema_path = schema_path / "coord_method_output_contract.v0.1.schema.json"
        for line in lines:
            record = json.loads(line)
            errs = validate_contract_record(record, schema_path=schema_path)
            assert not errs, f"Each line must validate: {errs}"
