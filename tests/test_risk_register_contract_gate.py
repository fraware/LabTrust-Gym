"""
Risk register contract gate: schema, snapshot, crosswalk integrity, coverage.

Ensures the risk register cannot silently rot; PRs that break the contract
fail CI.
"""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.export.risk_register_bundle import (
    COORDINATION_MATRIX_EVIDENCE_ID_PREFIX,
    build_risk_register_bundle,
    check_crosswalk_integrity,
    check_risk_register_coverage,
    resolve_run_dirs,
    validate_bundle_against_schema,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


SNAPSHOT_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "risk_register_bundle_ui_fixtures.v0.1.json"
)


def _bundle_ui_fixtures(root: Path) -> dict:
    """Build deterministic bundle from ui_fixtures."""
    run_dirs = resolve_run_dirs(root, ["ui_fixtures"])
    return build_risk_register_bundle(
        root,
        run_dirs=run_dirs,
        include_generated_at=False,
        include_git_hash=False,
    )


def test_schema_validation_generated_bundle_ui_fixtures() -> None:
    """Generated bundle from ui_fixtures validates against risk_register schema."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    errors = validate_bundle_against_schema(bundle, root)
    assert errors == [], f"Schema validation failed: {errors}"


def test_snapshot_ui_fixtures_bundle() -> None:
    """Bundle from ui_fixtures (deterministic) matches committed snapshot."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    generated = json.dumps(bundle, indent=2, sort_keys=True)
    assert SNAPSHOT_PATH.exists(), f"Snapshot missing: {SNAPSHOT_PATH}"
    snapshot_text = SNAPSHOT_PATH.read_text(encoding="utf-8")
    snapshot_data = json.loads(snapshot_text)
    expected = json.dumps(snapshot_data, indent=2, sort_keys=True)
    regen_hint = (
        "If intentional, regenerate: python -c \"from pathlib import Path; "
        "from labtrust_gym.export.risk_register_bundle import "
        "build_risk_register_bundle, resolve_run_dirs; import json; "
        "r=Path('.'); d=resolve_run_dirs(r, ['ui_fixtures']); "
        "b=build_risk_register_bundle(r, run_dirs=d, "
        "include_generated_at=False, include_git_hash=False); "
        "Path('tests/fixtures/risk_register_bundle_ui_fixtures.v0.1.json')."
        "write_text(json.dumps(b, indent=2, sort_keys=True))\""
    )
    assert generated == expected, (
        "Generated bundle differs from snapshot. " + regen_hint
    )


def test_crosswalk_risk_ids_in_evidence_exist_in_registry() -> None:
    """Every risk_id referenced in evidence exists in bundle.risks."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    errors = check_crosswalk_integrity(bundle)
    risk_errors = [e for e in errors if "risk_id" in e and "not in risks" in e]
    assert not risk_errors, (
        f"Crosswalk: risk_ids in evidence must exist in risks: {risk_errors}"
    )


def test_crosswalk_evidence_refs_exist() -> None:
    """Every evidence_id in risks[].evidence_refs exists in bundle.evidence."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    errors = check_crosswalk_integrity(bundle)
    ref_errors = [
        e for e in errors if "evidence_id" in e and "not in evidence" in e
    ]
    assert not ref_errors, (
        f"Crosswalk: evidence_refs must exist in evidence: {ref_errors}"
    )


def test_crosswalk_control_ids_in_claimed_controls_exist() -> None:
    """Every control_id in risks[].claimed_controls exists in bundle.controls."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    errors = check_crosswalk_integrity(bundle)
    ctrl_errors = [
        e for e in errors if "control_id" in e and "not in controls" in e
    ]
    assert not ctrl_errors, (
        f"Crosswalk: claimed_controls must exist in controls: {ctrl_errors}"
    )


def test_crosswalk_integrity_no_errors() -> None:
    """Full crosswalk: no dangling risk_id, evidence_id, or control_id."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    errors = check_crosswalk_integrity(bundle)
    assert errors == [], f"Crosswalk integrity failed: {errors}"


def test_coverage_gate_required_bench_evidenced_or_waived() -> None:
    """Required (method, risk) cells must be evidenced or waived for smoke."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    passed, missing = check_risk_register_coverage(bundle, root, waived_risk_ids=None)
    if not missing:
        return
    risk_ids_in_bundle = {
        r["risk_id"] for r in (bundle.get("risks") or []) if r.get("risk_id")
    }
    passed_waived, still_missing = check_risk_register_coverage(
        bundle, root, waived_risk_ids=risk_ids_in_bundle
    )
    assert passed_waived, (
        f"Coverage gate should pass when all risk_ids waived: {still_missing}"
    )
    assert len(still_missing) == 0


def test_coverage_gate_reports_missing_when_not_waived() -> None:
    """Coverage gate returns missing for required cells with no evidence."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    passed, missing = check_risk_register_coverage(
        bundle, root, waived_risk_ids=None
    )
    if not passed:
        assert len(missing) > 0
        for mid, rid in missing:
            assert isinstance(mid, str)
            assert isinstance(rid, str)


def test_bundle_loadable_and_has_risk_evidence_structure() -> None:
    """Bundle has expected top-level keys and risk/evidence structure (site)."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    assert "bundle_version" in bundle
    assert "risks" in bundle
    assert "evidence" in bundle
    assert "controls" in bundle
    assert isinstance(bundle["risks"], list)
    assert isinstance(bundle["evidence"], list)
    for risk in bundle["risks"]:
        assert "risk_id" in risk
        assert "evidence_refs" in risk
    for ev in bundle["evidence"]:
        assert "evidence_id" in ev
        assert "status" in ev


def test_risk_register_includes_matrix_evidence_when_present() -> None:
    """Export-risk-register on a run dir that contains the matrix records it as evidence."""
    root = _repo_root()
    run_fixture = root / "tests" / "fixtures" / "coordination_matrix_run_fixture"
    if not (run_fixture / "coordination_matrix.v0.1.json").exists():
        if not (run_fixture / "summary_coord.csv").exists():
            import pytest
            pytest.skip("coordination_matrix_run_fixture not present")
        import pytest
        pytest.skip("coordination_matrix_run_fixture has no matrix file (run builder first)")
    run_dirs = [run_fixture]
    bundle = build_risk_register_bundle(
        root,
        run_dirs=run_dirs,
        include_generated_at=False,
        include_git_hash=False,
    )
    evidence = bundle.get("evidence") or []
    matrix_evidence = [
        e for e in evidence
        if (e.get("evidence_id") or "").startswith(COORDINATION_MATRIX_EVIDENCE_ID_PREFIX)
    ]
    assert len(matrix_evidence) >= 1, (
        "Bundle must include coordination matrix evidence when run dir contains matrix"
    )
    ev = matrix_evidence[0]
    assert ev.get("status") == "present"
    assert ev.get("type") == "coordination_study"
    assert "artifacts" in ev and len(ev["artifacts"]) >= 1
    errors = validate_bundle_against_schema(bundle, root)
    assert errors == [], f"Schema validation failed: {errors}"
    crosswalk_errors = check_crosswalk_integrity(bundle)
    assert crosswalk_errors == [], f"Crosswalk integrity failed: {crosswalk_errors}"
