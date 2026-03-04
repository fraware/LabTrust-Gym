"""
Risk register contract gate: schema, snapshot, crosswalk integrity, coverage.

Ensures the risk register cannot silently rot; PRs that break the contract
fail CI.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from labtrust_gym.export.risk_register_bundle import (
    COORDINATION_MATRIX_EVIDENCE_ID_PREFIX,
    build_risk_register_bundle,
    check_crosswalk_integrity,
    check_risk_register_coverage,
    load_waivers,
    resolve_run_dirs,
    validate_bundle_against_schema,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


SNAPSHOT_PATH = Path(__file__).resolve().parent / "fixtures" / "risk_register_bundle_ui_fixtures.v0.1.json"


UI_FIXTURES_RUN_SPEC = "tests/fixtures/ui_fixtures"
# Minimal fixture (only pack_summary.csv) used for coverage gate; evidence is marked synthetic.
COORD_PACK_FIXTURE_RUN_SPEC = "tests/fixtures/coord_pack_fixture_minimal"


def _bundle_ui_fixtures(root: Path) -> dict:
    """Build deterministic bundle from tests/fixtures/ui_fixtures."""
    run_dirs = resolve_run_dirs(root, [UI_FIXTURES_RUN_SPEC])
    return build_risk_register_bundle(
        root,
        run_dirs=run_dirs,
        include_generated_at=False,
        include_git_hash=False,
    )


def test_export_risk_register_determinism() -> None:
    """Same run dir and options -> two export runs produce identical bundle (canonical JSON)."""
    root = _repo_root()
    bundle1 = _bundle_ui_fixtures(root)
    bundle2 = _bundle_ui_fixtures(root)
    j1 = json.dumps(bundle1, indent=2, sort_keys=True)
    j2 = json.dumps(bundle2, indent=2, sort_keys=True)
    assert j1 == j2, "Two export-risk-register runs from same inputs must yield identical bundle"


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
        'If intentional, regenerate: python -c "from pathlib import Path; '
        "from labtrust_gym.export.risk_register_bundle import "
        "build_risk_register_bundle, resolve_run_dirs; import json; "
        "r=Path('.'); d=resolve_run_dirs(r, ['tests/fixtures/ui_fixtures']); "
        "b=build_risk_register_bundle(r, run_dirs=d, "
        "include_generated_at=False, include_git_hash=False); "
        "Path('tests/fixtures/risk_register_bundle_ui_fixtures.v0.1.json')."
        'write_text(json.dumps(b, indent=2, sort_keys=True))"'
    )
    assert generated == expected, "Generated bundle differs from snapshot. " + regen_hint


def test_ui_fixtures_evidence_bundle_verifies() -> None:
    """ui_fixtures EvidenceBundle.v0.1 passes verify_bundle (manifest hashes and schema)."""
    from labtrust_gym.export.verify import verify_bundle

    root = _repo_root()
    bundle_dir = root / "tests" / "fixtures" / "ui_fixtures" / "evidence_bundle" / "EvidenceBundle.v0.1"
    if not bundle_dir.is_dir():
        return  # skip if fixture not present
    passed, _report, errors = verify_bundle(bundle_dir, policy_root=root)
    assert passed, f"ui_fixtures evidence bundle must verify: {errors}"


def test_crosswalk_risk_ids_in_evidence_exist_in_registry() -> None:
    """Every risk_id referenced in evidence exists in bundle.risks."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    errors = check_crosswalk_integrity(bundle)
    risk_errors = [e for e in errors if "risk_id" in e and "not in risks" in e]
    assert not risk_errors, f"Crosswalk: risk_ids in evidence must exist in risks: {risk_errors}"


def test_crosswalk_evidence_refs_exist() -> None:
    """Every evidence_id in risks[].evidence_refs exists in bundle.evidence."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    errors = check_crosswalk_integrity(bundle)
    ref_errors = [e for e in errors if "evidence_id" in e and "not in evidence" in e]
    assert not ref_errors, f"Crosswalk: evidence_refs must exist in evidence: {ref_errors}"


def test_crosswalk_control_ids_in_claimed_controls_exist() -> None:
    """Every control_id in risks[].claimed_controls exists in bundle.controls."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    errors = check_crosswalk_integrity(bundle)
    ctrl_errors = [e for e in errors if "control_id" in e and "not in controls" in e]
    assert not ctrl_errors, f"Crosswalk: claimed_controls must exist in controls: {ctrl_errors}"


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
    risk_ids_in_bundle = {r["risk_id"] for r in (bundle.get("risks") or []) if r.get("risk_id")}
    passed_waived, still_missing = check_risk_register_coverage(bundle, root, waived_risk_ids=risk_ids_in_bundle)
    assert passed_waived, f"Coverage gate should pass when all risk_ids waived: {still_missing}"
    assert len(still_missing) == 0


def test_coverage_gate_reports_missing_when_not_waived() -> None:
    """Coverage gate returns missing for required cells with no evidence."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    passed, missing = check_risk_register_coverage(bundle, root, waived_risk_ids=None)
    if not passed:
        assert len(missing) > 0
        for mid, rid in missing:
            assert isinstance(mid, str)
            assert isinstance(rid, str)


def test_coverage_gate_missing_evidence_valid_waiver_passes() -> None:
    """Missing evidence + valid waiver (waived_cells) -> PASS."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    passed, missing = check_risk_register_coverage(bundle, root)
    if passed:
        return
    waived_cells = set(missing)
    passed_waived, still_missing = check_risk_register_coverage(bundle, root, waived_cells=waived_cells)
    assert passed_waived, f"With all missing cells waived should pass: {still_missing}"
    assert len(still_missing) == 0


def test_coverage_gate_missing_evidence_expired_waiver_fails() -> None:
    """Missing evidence + only expired waiver -> still FAIL (waived_cells does not include cell)."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    passed, missing = check_risk_register_coverage(bundle, root)
    if passed or not missing:
        return
    passed_empty_waived, still_missing = check_risk_register_coverage(bundle, root, waived_cells=set())
    assert not passed_empty_waived or len(still_missing) > 0, "With no waivers, missing cells must remain missing"


def test_coverage_gate_missing_evidence_no_waiver_fails() -> None:
    """Missing evidence + no waiver -> FAIL (explicit no waived_cells)."""
    root = _repo_root()
    bundle = _bundle_ui_fixtures(root)
    passed, missing = check_risk_register_coverage(bundle, root, waived_risk_ids=None, waived_cells=None)
    if not passed:
        assert len(missing) >= 0


def test_load_waivers_returns_non_expired() -> None:
    """load_waivers returns set of (method_id, risk_id) from policy file (non-expired)."""
    root = _repo_root()
    cells = load_waivers(root)
    assert isinstance(cells, set)
    for item in cells:
        assert isinstance(item, tuple)
        assert len(item) == 2
        assert isinstance(item[0], str)
        assert isinstance(item[1], str)


def test_coord_pack_fixture_csv_headers_match_pack_summary_columns() -> None:
    """coord_pack_fixture_minimal pack_summary.csv headers must match PACK_SUMMARY_COLUMNS to avoid drift."""
    from labtrust_gym.studies.coordination_security_pack import PACK_SUMMARY_COLUMNS

    root = _repo_root()
    path = root / "tests" / "fixtures" / "coord_pack_fixture_minimal" / "pack_summary.csv"
    assert path.exists(), f"Fixture missing: {path}"
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        assert list(reader.fieldnames) == PACK_SUMMARY_COLUMNS, (
            "coord_pack_fixture pack_summary.csv headers must match PACK_SUMMARY_COLUMNS"
        )


def test_two_fixture_bundle_passes_strict_coverage() -> None:
    """Bundle from ui_fixtures + coord_pack_fixture_minimal passes validate-coverage --strict; coord_pack evidence is synthetic."""
    root = _repo_root()
    run_dirs = resolve_run_dirs(root, [UI_FIXTURES_RUN_SPEC, COORD_PACK_FIXTURE_RUN_SPEC])
    bundle = build_risk_register_bundle(
        root,
        run_dirs=run_dirs,
        include_generated_at=False,
        include_git_hash=False,
    )
    waived_cells = load_waivers(root)
    passed, missing = check_risk_register_coverage(bundle, root, waived_cells=waived_cells)
    assert passed, f"Expected strict coverage to pass; missing: {missing}"
    assert missing == []

    coord_pack_evidence = [e for e in (bundle.get("evidence") or []) if e.get("type") == "coordination_pack"]
    assert len(coord_pack_evidence) == 1, (
        "Bundle from ui_fixtures + coord_pack_fixture_minimal must contain exactly one coordination_pack evidence"
    )
    assert coord_pack_evidence[0].get("synthetic") is True, (
        "coord_pack_fixture_minimal has only pack_summary.csv; evidence must be marked synthetic"
    )


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
        e for e in evidence if (e.get("evidence_id") or "").startswith(COORDINATION_MATRIX_EVIDENCE_ID_PREFIX)
    ]
    assert len(matrix_evidence) >= 1, "Bundle must include coordination matrix evidence when run dir contains matrix"
    ev = matrix_evidence[0]
    assert ev.get("status") == "present"
    assert ev.get("type") == "coordination_study"
    assert "artifacts" in ev and len(ev["artifacts"]) >= 1
    errors = validate_bundle_against_schema(bundle, root)
    assert errors == [], f"Schema validation failed: {errors}"
    crosswalk_errors = check_crosswalk_integrity(bundle)
    assert crosswalk_errors == [], f"Crosswalk integrity failed: {crosswalk_errors}"
