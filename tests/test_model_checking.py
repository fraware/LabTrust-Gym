"""
Tests for the bounded trace invariant checker (check_critical_path_safety).

Covers passing traces (no violations for checked invariants) and failing traces
(non-trivial violations with invariant_id, reason_code, evidence).
"""

import importlib.util
import sys
from pathlib import Path

# Load model_checking without importing labtrust_gym.engine (avoids circular import).
_engine_dir = Path(__file__).resolve().parent.parent / "src" / "labtrust_gym" / "engine"
_spec = importlib.util.spec_from_file_location(
    "labtrust_gym.engine.model_checking",
    _engine_dir / "model_checking.py",
    submodule_search_locations=[str(_engine_dir)],
)
_model_checking = importlib.util.module_from_spec(_spec)
sys.modules["labtrust_gym.engine.model_checking"] = _model_checking
_spec.loader.exec_module(_model_checking)

Violation = _model_checking.Violation
check_critical_path_safety = _model_checking.check_critical_path_safety


def _trace_entry(
    event_id: str = "ev-1",
    t_s: int = 0,
    agent_id: str = "A1",
    action_type: str = "MOVE",
    status: str = "ok",
    violations: list[dict] | None = None,
) -> dict:
    return {
        "event": {
            "event_id": event_id,
            "t_s": t_s,
            "agent_id": agent_id,
            "action_type": action_type,
        },
        "result": {
            "status": status,
            "violations": violations or [],
        },
    }


# Invariant IDs that exist in policy/invariants (for meaningful messages)
INV_ZONE_001 = "INV-ZONE-001"
INV_ZONE_002 = "INV-ZONE-002"


# ----- Passing traces (no VIOLATION for checked invariant_ids) -----


def test_check_critical_path_safety_passing_empty_trace():
    """Passing: empty trace has no violations."""
    safe, trace, violations = check_critical_path_safety(
        event_trace=[],
        invariant_ids=[INV_ZONE_001, INV_ZONE_002],
        max_steps=10,
    )
    assert safe is True
    assert trace == []
    assert violations == []


def test_check_critical_path_safety_passing_all_pass():
    """Passing: trace with only PASS or unrelated violations."""
    trace = [
        _trace_entry("ev-1", 0, "A1", "MOVE", "ok", []),
        _trace_entry(
            "ev-2",
            1,
            "A1",
            "MOVE",
            "ok",
            [
                {"invariant_id": INV_ZONE_001, "status": "PASS", "reason_code": "OK"},
            ],
        ),
        _trace_entry(
            "ev-3",
            2,
            "A2",
            "CENTRIFUGE_START",
            "ok",
            [
                {"invariant_id": "OTHER-INV", "status": "VIOLATION", "reason_code": "X"},
            ],
        ),
    ]
    safe, bounded, violations = check_critical_path_safety(
        event_trace=trace,
        invariant_ids=[INV_ZONE_001, INV_ZONE_002],
        max_steps=10,
    )
    assert safe is True
    assert len(bounded) == 3
    assert violations == []


# ----- Failing traces (non-trivial violations) -----


def test_check_critical_path_safety_failing_single_violation():
    """Failing: one step violates INV-ZONE-001 with reason_code and evidence."""
    trace = [
        _trace_entry("ev-1", 0, "A1", "MOVE", "ok", []),
        _trace_entry(
            "ev-2",
            1,
            "A1",
            "MOVE",
            "blocked",
            [
                {
                    "invariant_id": INV_ZONE_001,
                    "status": "VIOLATION",
                    "reason_code": "RC_ILLEGAL_MOVE",
                    "message": "from_zone not adjacent to to_zone",
                },
            ],
        ),
    ]
    safe, bounded, violations = check_critical_path_safety(
        event_trace=trace,
        invariant_ids=[INV_ZONE_001, INV_ZONE_002],
        max_steps=10,
    )
    assert safe is False
    assert len(bounded) == 2
    assert len(violations) == 1
    v = violations[0]
    assert v.invariant_id == INV_ZONE_001
    assert v.step_index == 1
    assert "Movement must follow permitted edges" in v.message or INV_ZONE_001 in v.message
    assert v.evidence.get("event_id") == "ev-2"
    assert v.evidence.get("action_type") == "MOVE"
    assert v.evidence.get("t_s") == 1


def test_check_critical_path_safety_failing_multiple_steps_and_ids():
    """Failing: multiple steps violate different checked invariants."""
    trace = [
        _trace_entry("ev-0", 0, "A1", "MOVE", "ok", []),
        _trace_entry(
            "ev-1",
            1,
            "A1",
            "CENTRIFUGE_START",
            "blocked",
            [
                {
                    "invariant_id": INV_ZONE_002,
                    "status": "VIOLATION",
                    "reason_code": "RC_DEVICE_NOT_COLOCATED",
                    "details": {"zone": "Z_LAB", "device_zone": "Z_CENTRIFUGE"},
                },
            ],
        ),
        _trace_entry("ev-2", 2, "A1", "MOVE", "ok", []),
        _trace_entry(
            "ev-3",
            3,
            "A2",
            "MOVE",
            "blocked",
            [
                {
                    "invariant_id": INV_ZONE_001,
                    "status": "VIOLATION",
                    "reason_code": "RC_ILLEGAL_MOVE",
                },
            ],
        ),
    ]
    safe, bounded, violations = check_critical_path_safety(
        event_trace=trace,
        invariant_ids=[INV_ZONE_001, INV_ZONE_002],
        max_steps=10,
    )
    assert safe is False
    assert len(bounded) == 4
    assert len(violations) == 2
    by_step = {v.step_index: v for v in violations}
    assert 1 in by_step and by_step[1].invariant_id == INV_ZONE_002
    assert 3 in by_step and by_step[3].invariant_id == INV_ZONE_001
    v1 = by_step[1]
    assert "Device operations require co-location" in v1.message or INV_ZONE_002 in v1.message
    assert v1.evidence.get("details") == {"zone": "Z_LAB", "device_zone": "Z_CENTRIFUGE"}


# ----- Bounded steps and output artifacts -----


def test_check_critical_path_safety_respects_max_steps():
    """Trace is truncated to max_steps; only those steps are checked."""
    trace = [_trace_entry(f"ev-{i}", i, "A1", "MOVE", "ok", []) for i in range(20)]
    trace[5]["result"]["violations"] = [
        {"invariant_id": INV_ZONE_001, "status": "VIOLATION", "reason_code": "R"},
    ]
    safe, bounded, violations = check_critical_path_safety(
        event_trace=trace,
        invariant_ids=[INV_ZONE_001],
        max_steps=4,
    )
    assert safe is True
    assert len(bounded) == 5  # 0..max_steps inclusive
    assert violations == []

    safe2, bounded2, violations2 = check_critical_path_safety(
        event_trace=trace,
        invariant_ids=[INV_ZONE_001],
        max_steps=10,
    )
    assert safe2 is False
    assert len(violations2) == 1
    assert violations2[0].step_index == 5


def test_check_critical_path_safety_emits_report_artifacts(tmp_path):
    """When output_dir is set, model_check_report.json and .md are written."""
    trace = [
        _trace_entry("ev-1", 0, "A1", "MOVE", "ok", []),
        _trace_entry(
            "ev-2",
            1,
            "A1",
            "MOVE",
            "blocked",
            [
                {
                    "invariant_id": INV_ZONE_001,
                    "status": "VIOLATION",
                    "reason_code": "RC_ILLEGAL_MOVE",
                },
            ],
        ),
    ]
    check_critical_path_safety(
        event_trace=trace,
        invariant_ids=[INV_ZONE_001],
        max_steps=10,
        output_dir=tmp_path,
    )
    json_path = tmp_path / "model_check_report.json"
    md_path = tmp_path / "model_check_report.md"
    assert json_path.exists()
    assert md_path.exists()
    import json as _json

    report = _json.loads(json_path.read_text())
    assert report["safe"] is False
    assert report["steps_checked"] == 2
    assert len(report["violations"]) == 1
    assert report["violations"][0]["invariant_id"] == INV_ZONE_001
    md = md_path.read_text()
    assert "Model check report" in md
    assert "False" in md and "Safe" in md
    assert "Violations" in md
    assert INV_ZONE_001 in md


def test_violation_to_dict():
    """Violation.to_dict() returns a serializable dict."""
    v = Violation(
        invariant_id="INV-X",
        step_index=2,
        evidence={"event_id": "e1", "t_s": 1},
        message="Test message",
    )
    d = v.to_dict()
    assert d["invariant_id"] == "INV-X"
    assert d["step_index"] == 2
    assert d["evidence"]["event_id"] == "e1"
    assert d["message"] == "Test message"
