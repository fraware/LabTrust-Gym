"""LTG-PR3 golden-suite governance: schema fields and hazard coverage gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.policy.golden_governance import (
    COVERAGE_CLASSES,
    validate_golden_hazard_coverage_gate,
)
from labtrust_gym.policy.loader import load_yaml
from labtrust_gym.policy.validate import validate_golden_scenarios, validate_policy


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


REQUIRED_GOV_KEYS = (
    "hazard",
    "policy_version",
    "action_sequence",
    "expected_reason_codes",
    "expected_terminal_state",
    "required_evidence",
    "coverage_class",
    "reviewer",
)


def test_every_golden_scenario_has_governance_metadata() -> None:
    root = _repo_root()
    data = load_yaml(root / "policy" / "golden" / "golden_scenarios.v0.1.yaml")
    suite = data["golden_suite"]
    assert "governance" in suite
    scenarios = suite["scenarios"]
    assert len(scenarios) >= 1
    for sc in scenarios:
        sid = sc["scenario_id"]
        gov = sc["governance"]
        for key in REQUIRED_GOV_KEYS:
            assert key in gov, f"{sid}: missing governance.{key}"
        assert gov["coverage_class"] in COVERAGE_CLASSES
        assert isinstance(gov["action_sequence"], list) and gov["action_sequence"]
        assert isinstance(gov["expected_reason_codes"], list)
        assert isinstance(gov["required_evidence"], list) and gov["required_evidence"]
        derived = [step["action_type"] for step in sc["script"]]
        assert gov["action_sequence"] == derived, f"{sid}: action_sequence drift"


def test_golden_hazard_coverage_gate_passes() -> None:
    errors = validate_golden_hazard_coverage_gate(_repo_root())
    assert errors == [], errors


def test_validate_golden_scenarios_includes_coverage_gate() -> None:
    errors = validate_golden_scenarios(_repo_root())
    assert errors == [], errors


def test_coverage_gate_fails_when_scenario_claims_unlisted_class(tmp_path: Path) -> None:
    """Fail-closed: claiming a class without a matrix listing must error."""
    root = _repo_root()
    # Build a minimal mirror with one scenario claiming catalog_drift (uncovered / empty GS list).
    policy = tmp_path / "policy"
    (policy / "golden").mkdir(parents=True)
    (policy / "coverage").mkdir(parents=True)
    golden = {
        "golden_suite": {
            "version": "0.1",
            "scenarios": [
                {
                    "scenario_id": "GS-FAKE",
                    "initial_state": {},
                    "script": [
                        {
                            "event_id": "e1",
                            "t_s": 0,
                            "agent_id": "A",
                            "action_type": "TICK",
                            "args": {},
                            "reason_code": None,
                            "token_refs": [],
                        }
                    ],
                    "governance": {
                        "hazard": "fake",
                        "policy_version": "0.1",
                        "action_sequence": ["TICK"],
                        "expected_reason_codes": [],
                        "expected_terminal_state": "done",
                        "required_evidence": ["none"],
                        "coverage_class": "catalog_drift",
                        "reviewer": "pending-domain-review",
                    },
                }
            ],
        }
    }
    matrix = load_yaml(root / "policy" / "coverage" / "hazard_coverage_matrix.v0.1.yaml")
    import yaml

    (policy / "golden" / "golden_scenarios.v0.1.yaml").write_text(
        yaml.safe_dump(golden), encoding="utf-8"
    )
    (policy / "coverage" / "hazard_coverage_matrix.v0.1.yaml").write_text(
        yaml.safe_dump(matrix), encoding="utf-8"
    )
    errors = validate_golden_hazard_coverage_gate(tmp_path)
    assert errors, "expected coverage gate failure"
    assert any("GS-FAKE" in e and "catalog_drift" in e for e in errors)


def test_coverage_gate_fails_when_uncovered_class_lists_scenarios(tmp_path: Path) -> None:
    root = _repo_root()
    policy = tmp_path / "policy"
    (policy / "golden").mkdir(parents=True)
    (policy / "coverage").mkdir(parents=True)
    # Copy real golden (valid) but break catalog_drift uncovered invariant.
    import shutil

    shutil.copy(
        root / "policy" / "golden" / "golden_scenarios.v0.1.yaml",
        policy / "golden" / "golden_scenarios.v0.1.yaml",
    )
    matrix = load_yaml(root / "policy" / "coverage" / "hazard_coverage_matrix.v0.1.yaml")
    for row in matrix["hazard_coverage_matrix"]["hazards"]:
        if row["hazard_class"] == "catalog_drift":
            row["golden_scenario_ids"] = ["GS-001"]
            row["gap"] = "should not list GS while uncovered"
            break
    import yaml

    (policy / "coverage" / "hazard_coverage_matrix.v0.1.yaml").write_text(
        yaml.safe_dump(matrix), encoding="utf-8"
    )
    errors = validate_golden_hazard_coverage_gate(tmp_path)
    assert any("uncovered must not list" in e for e in errors)


def test_governance_doc_exists() -> None:
    path = _repo_root() / "docs" / "benchmarks" / "golden_suite_governance.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "coverage gate" in text.lower() or "Coverage gate" in text
    assert "catalog_drift" in text


@pytest.mark.parametrize("rel", ["docs/benchmarks/scientific_credibility.md", "docs/reference/testing_strategy.md"])
def test_governance_doc_linked_from_program_docs(rel: str) -> None:
    text = (_repo_root() / rel).read_text(encoding="utf-8")
    assert "golden_suite_governance" in text


def test_validate_policy_still_passes_with_governance_gate() -> None:
    errors = validate_policy(_repo_root())
    assert errors == [], errors
