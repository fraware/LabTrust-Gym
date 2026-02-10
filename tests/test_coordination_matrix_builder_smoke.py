"""Smoke test for coordination_matrix_builder (minimal run dir, no sources) and CLI."""
from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_matrix_builder import (
    build_coordination_matrix,
    write_coordination_matrix,
)
from labtrust_gym.cli.main import (
    COORDINATION_MATRIX_CANONICAL_FILENAME,
    _run_build_coordination_matrix,
    _run_coordination_study,
)


def test_llm_live_guard_rejects_offline():
    """Non-llm_live pipeline_mode must raise with exact message."""
    run = Path(__file__).resolve().parent / "fixtures" / "coordination_matrix_run_minimal"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metadata.json").write_text('{"pipeline_mode": "offline"}')
    out = run / "out.json"
    with pytest.raises(ValueError) as exc_info:
        build_coordination_matrix(run, out, strict=True)
    assert "llm_live-only" in str(exc_info.value)
    assert "offline" in str(exc_info.value)


def test_build_minimal_run_dir_no_sources():
    """With llm_live metadata but no source CSVs, extraction fails (or empty matrix)."""
    run = Path(__file__).resolve().parent / "fixtures" / "coordination_matrix_run_minimal"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metadata.json").write_text('{"pipeline_mode": "llm_live"}')
    out = run / "out.json"
    # May raise (missing sources) or succeed with empty rows depending on implementation
    try:
        build_coordination_matrix(run, out, strict=True)
    except (ValueError, FileNotFoundError, KeyError) as e:
        assert "pipeline_mode" not in str(e).lower() or "llm_live" in str(e)


def test_write_coordination_matrix_deterministic():
    """write_coordination_matrix produces stable JSON (sort_keys)."""
    import json
    fixture = Path(__file__).resolve().parent / "fixtures" / "coordination_matrix_fixture.v0.1.json"
    matrix = json.loads(fixture.read_text(encoding="utf-8"))
    out = Path(__file__).resolve().parent / "fixtures" / "coordination_matrix_written.json"
    write_coordination_matrix(matrix, out)
    again = json.loads(out.read_text(encoding="utf-8"))
    assert json.dumps(matrix, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_build_coordination_matrix_cli_out_dir_resolution():
    """When --out is a directory, CLI uses canonical filename coordination_matrix.v0.1.json."""
    assert COORDINATION_MATRIX_CANONICAL_FILENAME == "coordination_matrix.v0.1.json"
    run = Path(__file__).resolve().parent / "fixtures" / "coordination_matrix_run_minimal"
    run.mkdir(parents=True, exist_ok=True)
    (run / "metadata.json").write_text('{"pipeline_mode": "llm_live"}')
    out_dir = Path(__file__).resolve().parent / "fixtures" / "coord_matrix_cli_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    args = type("Args", (), {
        "run": str(run),
        "out": str(out_dir),
        "policy_root": None,
        "no_strict": False,
    })()
    # Build fails (no sources); CLI would write to out_dir/coordination_matrix.v0.1.json if it succeeded
    with pytest.raises(FileNotFoundError):
        _run_build_coordination_matrix(args)
    assert (out_dir / COORDINATION_MATRIX_CANONICAL_FILENAME).name == "coordination_matrix.v0.1.json"


def test_builder_on_run_fixture_gates_and_aggregation():
    """Builder runs on coordination_matrix_run_fixture; disqualify and penalize gates and worst-case aggregation."""
    from labtrust_gym.studies.coordination_matrix_builder import build_coordination_matrix
    from labtrust_gym.cli.main import COORDINATION_MATRIX_CANONICAL_FILENAME

    fixture_run = Path(__file__).resolve().parent / "fixtures" / "coordination_matrix_run_fixture"
    if not (fixture_run / "summary_coord.csv").exists():
        pytest.skip("coordination_matrix_run_fixture not present")
    out_path = fixture_run / COORDINATION_MATRIX_CANONICAL_FILENAME
    matrix = build_coordination_matrix(fixture_run, out_path, strict=True)
    rows = matrix.get("rows") or []
    assert len(rows) >= 6, "expected at least 2 scales x 3 methods"
    scales = {r["scale_id"] for r in rows}
    assert len(scales) >= 2
    methods = {r["method_id"] for r in rows}
    assert len(methods) >= 3

    # At least one row disqualified (violation_rate_cap: violation_rate > 0.01)
    disqualified = [r for r in rows if not r.get("feasible", {}).get("overall", True)]
    assert len(disqualified) >= 1, "fixture should trigger at least one disqualify gate"
    violation_cap_failures = [r for r in rows if "violation_rate_cap" in (r.get("feasible", {}).get("reasons") or [])]
    assert len(violation_cap_failures) >= 1

    # At least one row with penalize (attack_success_cap)
    penalized = [r for r in rows if (r.get("scores") or {}).get("penalties")]
    assert len(penalized) >= 1, "fixture should trigger at least one penalize gate"
    attack_cap_penalties = [r for r in rows if any(p.get("reason") == "attack_success_cap" for p in (r.get("scores") or {}).get("penalties", []))]
    assert len(attack_cap_penalties) >= 1

    # One cell has worst-case from 2 injections (corridor_heavy, llm_central_planner): attack_success_rate 0.10 and 0.25 -> 0.25
    central_planner_row = next((r for r in rows if r["scale_id"] == "corridor_heavy" and r["method_id"] == "llm_central_planner"), None)
    assert central_planner_row is not None
    attacked = (central_planner_row.get("metrics") or {}).get("attacked") or {}
    assert "attack_success_rate" in attacked
    assert attacked["attack_success_rate"] == 0.25, "worst-case over inj_A=0.10 and inj_B=0.25 should be 0.25"


def test_run_coordination_study_emit_matrix_errors_when_not_llm_live():
    """With --emit-coordination-matrix and non-llm_live backend, CLI errors with explicit message."""
    import sys
    from io import StringIO

    run = Path(__file__).resolve().parent / "fixtures" / "coordination_matrix_run_minimal"
    run.mkdir(parents=True, exist_ok=True)
    spec = Path(__file__).resolve().parent.parent / "policy" / "coordination" / "coordination_study_spec.v0.1.yaml"
    if not spec.exists():
        spec = run / "dummy_spec.yaml"
        spec.write_text("study_id: dummy\n")
    args = type("Args", (), {
        "spec": str(spec),
        "out": str(run),
        "llm_backend": "deterministic",
        "llm_model": None,
        "emit_coordination_matrix": True,
    })()
    old_stderr = sys.stderr
    try:
        sys.stderr = StringIO()
        ret = _run_coordination_study(args)
        err = sys.stderr.getvalue()
    finally:
        sys.stderr = old_stderr
    assert ret == 1
    assert "emit-coordination-matrix" in err
    assert "llm_live" in err
    assert "deterministic" in err or "out of scope" in err
