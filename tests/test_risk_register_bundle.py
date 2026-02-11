"""
Risk register bundle: build from policy and run dirs; schema validation; determinism.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.export.risk_register_bundle import (
    RISK_REGISTER_BUNDLE_FILENAME,
    build_risk_register_bundle,
    export_risk_register,
    validate_bundle_against_schema,
    write_risk_register_bundle,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_build_risk_register_bundle_from_repo_root() -> None:
    """Build with no run dirs yields bundle with required keys and structure."""
    root = _repo_root()
    bundle = build_risk_register_bundle(
        root,
        run_dirs=[],
        include_generated_at=False,
        include_git_hash=False,
    )
    assert bundle["bundle_version"] == "0.1"
    assert "risks" in bundle
    assert "controls" in bundle
    assert "evidence" in bundle
    assert isinstance(bundle["risks"], list)
    assert isinstance(bundle["controls"], list)
    assert isinstance(bundle["evidence"], list)
    assert len(bundle["risks"]) >= 1
    for risk in bundle["risks"]:
        assert "risk_id" in risk
        assert "name" in risk
        assert risk["risk_domain"] in {
            "tool", "flow", "system", "comms", "identity", "data", "capability", "operational",
        }
        assert "applies_to" in risk
        assert "claimed_controls" in risk
        assert "evidence_refs" in risk
        assert risk["coverage_status"] in {
            "covered", "partially_covered", "uncovered", "not_applicable",
        }
    for ctrl in bundle["controls"]:
        assert "control_id" in ctrl
        assert "name" in ctrl
        assert ctrl.get("source") in ("security_suite", "safety_case", None)


def test_bundle_validates_against_schema() -> None:
    """Built bundle passes schema validation."""
    root = _repo_root()
    bundle = build_risk_register_bundle(
        root,
        run_dirs=[],
        include_generated_at=False,
        include_git_hash=False,
    )
    errors = validate_bundle_against_schema(bundle, root)
    assert errors == [], f"Schema validation failed: {errors}"


def test_bundle_deterministic_without_timestamp_and_git() -> None:
    """Two builds with same policy and no run dirs yield identical JSON (no generated_at, no git)."""
    root = _repo_root()
    b1 = build_risk_register_bundle(
        root,
        run_dirs=[],
        include_generated_at=False,
        include_git_hash=False,
    )
    b2 = build_risk_register_bundle(
        root,
        run_dirs=[],
        include_generated_at=False,
        include_git_hash=False,
    )
    j1 = json.dumps(b1, indent=2, sort_keys=True)
    j2 = json.dumps(b2, indent=2, sort_keys=True)
    assert j1 == j2, "Bundle build should be deterministic when policy and run_dirs are fixed"


def test_build_with_run_dir_containing_security(tmp_path: Path) -> None:
    """Build with a run dir containing SECURITY/attack_results.json adds security evidence and risk refs."""
    root = _repo_root()
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    security_dir = run_dir / "SECURITY"
    security_dir.mkdir()
    # Minimal attack_results.json: one result for a risk that exists in registry (R-CAP-001)
    attack_results = {
        "version": "0.1",
        "results": [
            {"attack_id": "SEC-PI-001", "passed": True, "risk_id": "R-CAP-001"},
        ],
        "summary": {"total": 1, "passed": 1, "failed": 0},
    }
    (security_dir / "attack_results.json").write_text(
        json.dumps(attack_results, indent=2),
        encoding="utf-8",
    )
    bundle = build_risk_register_bundle(
        root,
        run_dirs=[run_dir],
        include_generated_at=False,
        include_git_hash=False,
    )
    evidence_ids = [e["evidence_id"] for e in bundle["evidence"]]
    security_evidence = [e for e in bundle["evidence"] if e.get("type") == "security_suite"]
    assert len(security_evidence) >= 1
    risk_cap = next((r for r in bundle["risks"] if r["risk_id"] == "R-CAP-001"), None)
    assert risk_cap is not None
    assert any(ref in evidence_ids for ref in risk_cap["evidence_refs"]), (
        "R-CAP-001 should have at least one evidence_ref from attack_results"
    )


def test_write_risk_register_bundle_validates_by_default(tmp_path: Path) -> None:
    """write_risk_register_bundle produces valid JSON file and runs validation when validate=True."""
    root = _repo_root()
    out_path = tmp_path / "risk_register_bundle.v0.1.json"
    write_risk_register_bundle(
        repo_root=root,
        out_path=out_path,
        run_dirs=[],
        include_generated_at=False,
        include_git_hash=False,
        validate=True,
    )
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["bundle_version"] == "0.1"
    assert "risks" in data


def test_export_risk_register_ui_fixtures() -> None:
    """Running export-risk-register on tests/fixtures/ui_fixtures produces valid bundle with at least a few populated evidence refs."""
    root = _repo_root()
    ui_fixtures = root / "tests" / "fixtures" / "ui_fixtures"
    if not ui_fixtures.is_dir():
        pytest.skip("tests/fixtures/ui_fixtures/ not found")
    out_dir = root / "labtrust_runs" / "risk_export_test"
    out_path = export_risk_register(
        repo_root=root,
        out_dir=out_dir,
        run_specs=["tests/fixtures/ui_fixtures"],
        include_generated_at=False,
        include_git_hash=False,
        validate=True,
    )
    assert out_path == out_dir / RISK_REGISTER_BUNDLE_FILENAME
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["bundle_version"] == "0.1"
    present_evidence = [e for e in data["evidence"] if e.get("status") == "present"]
    assert len(present_evidence) >= 1, "tests/fixtures/ui_fixtures has SECURITY/attack_results.json so at least one present evidence"
    risk_cap = next((r for r in data["risks"] if r["risk_id"] == "R-CAP-001"), None)
    assert risk_cap is not None
    refs = risk_cap.get("evidence_refs") or []
    present_ids = {e["evidence_id"] for e in present_evidence}
    assert any(ref in present_ids for ref in refs), "R-CAP-001 should have at least one ref to present evidence"


def test_export_risk_register_rich_bundle(tmp_path: Path) -> None:
    """Export with SECURITY + SAFETY_CASE + MANIFEST produces security_suite, safety_case, bundle_verification evidence."""
    root = _repo_root()
    run_dir = tmp_path / "paper_release"
    run_dir.mkdir()
    (run_dir / "SECURITY").mkdir()
    (run_dir / "SECURITY" / "attack_results.json").write_text(
        json.dumps(
            {"version": "0.1", "results": [], "summary": {"total": 0, "passed": 0, "failed": 0}},
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "SAFETY_CASE").mkdir()
    (run_dir / "SAFETY_CASE" / "safety_case.json").write_text(
        json.dumps({"version": "0.1", "claims": []}, indent=2),
        encoding="utf-8",
    )
    (run_dir / "MANIFEST.v0.1.json").write_text(
        json.dumps({"version": "0.1", "files": [{"path": "SECURITY/attack_results.json", "sha256": "abc"}]}),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    export_risk_register(
        repo_root=root,
        out_dir=out_dir,
        run_specs=[str(run_dir)],
        include_generated_at=False,
        include_git_hash=False,
        validate=True,
    )
    data = json.loads((out_dir / RISK_REGISTER_BUNDLE_FILENAME).read_text(encoding="utf-8"))
    types = {e.get("type") for e in data["evidence"] if e.get("status") == "present"}
    assert "security_suite" in types
    assert "safety_case" in types
    assert "bundle_verification" in types
    assert "reproduce" in data
    repro_by_evidence = {r["evidence_id"]: r for r in data["reproduce"]}
    assert len(repro_by_evidence) >= 1
    # At least one present evidence has reproduction commands
    for e in data["evidence"]:
        if e.get("status") == "present" and e.get("type") == "security_suite":
            r = repro_by_evidence.get(e["evidence_id"])
            assert r is not None and len(r.get("commands", [])) >= 1
            break


def test_coord_summary_includes_metrics(tmp_path: Path) -> None:
    """When summary_coord.csv exists, coordination evidence has summary.coord_metrics (security + resilience)."""
    root = _repo_root()
    run_dir = tmp_path / "coord_run"
    run_dir.mkdir()
    (run_dir / "summary").mkdir()
    csv_path = run_dir / "summary" / "summary_coord.csv"
    csv_path.write_text(
        "method_id,scale_id,risk_id,injection_id,perf.throughput,perf.p95_tat,safety.violations_total,"
        "safety.blocks_total,sec.attack_success_rate,sec.detection_latency_steps,sec.containment_time_steps,"
        "sec.stealth_success_rate,sec.time_to_attribution_steps,sec.blast_radius_proxy,robustness.resilience_score\n"
        "whca,scale1,R-TOOL-001,inj1,2.0,10.5,0,1,0.0,,,0.0,5,2,0.85\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    export_risk_register(
        repo_root=root,
        out_dir=out_dir,
        run_specs=[str(run_dir)],
        include_generated_at=False,
        include_git_hash=False,
        validate=True,
    )
    data = json.loads((out_dir / RISK_REGISTER_BUNDLE_FILENAME).read_text(encoding="utf-8"))
    coord_evidence = [e for e in data["evidence"] if e.get("type") == "coordination_study" and e.get("path", "").endswith("summary_coord.csv")]
    assert len(coord_evidence) >= 1
    e = coord_evidence[0]
    assert "summary" in e and "coord_metrics" in e["summary"]
    rows = e["summary"]["coord_metrics"]
    assert len(rows) >= 1
    row = rows[0]
    assert "sec.attack_success_rate" in row or "robustness.resilience_score" in row
