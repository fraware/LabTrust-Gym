"""LTG-PR8 independent review gate: materials, unsigned slots, claim fail-closed."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from labtrust_gym.policy.independent_review import (
    assert_scientifically_reviewed_claim_allowed,
    scientifically_reviewed_claim_allowed,
    validate_independent_review_gate,
)
from labtrust_gym.policy.loader import PolicyLoadError
from labtrust_gym.policy.validate import validate_policy


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


REQUIRED_DOCS = (
    "docs/reviews/README.md",
    "docs/reviews/charter.md",
    "docs/reviews/invitation_template.md",
    "docs/reviews/protocol_and_checklist.md",
    "docs/reviews/signed_approval_gate.md",
)

REQUIRED_SLOTS = (
    "benchmarks/reviews/slots/laboratory_workflow_expert.UNSIGNED.json",
    "benchmarks/reviews/slots/safety_or_quality_specialist.UNSIGNED.json",
    "benchmarks/reviews/slots/multi_agent_benchmark_reviewer.UNSIGNED.json",
)


def test_independent_review_docs_and_slots_exist() -> None:
    root = _repo_root()
    for rel in REQUIRED_DOCS + REQUIRED_SLOTS + ("benchmarks/reviews/review_registry.v1.json",):
        assert (root / rel).is_file(), rel


def test_independent_review_gate_passes_with_unsigned_slots() -> None:
    errors = validate_independent_review_gate(_repo_root())
    assert errors == [], errors


def test_scientifically_reviewed_claim_not_allowed_yet() -> None:
    root = _repo_root()
    assert scientifically_reviewed_claim_allowed(root) is False
    with pytest.raises(PolicyLoadError, match="scientifically_reviewed_claim_allowed is false"):
        assert_scientifically_reviewed_claim_allowed(root)


def test_validate_policy_includes_independent_review_gate() -> None:
    errors = validate_policy(_repo_root())
    assert errors == [], errors


def test_registry_claim_true_with_unsigned_slots_fails(tmp_path: Path) -> None:
    root = _repo_root()
    # Mirror minimal tree required by the gate.
    for rel in REQUIRED_DOCS:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(root / rel, dest)
    for rel in (
        "policy/schemas/independent_review_report.v1.schema.json",
        "policy/schemas/independent_review_registry.v1.schema.json",
        "benchmarks/reviews/review_registry.v1.json",
        *REQUIRED_SLOTS,
    ):
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(root / rel, dest)

    registry_path = tmp_path / "benchmarks" / "reviews" / "review_registry.v1.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["scientifically_reviewed_claim_allowed"] = True
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    errors = validate_independent_review_gate(tmp_path)
    assert errors, "expected fail-closed claim error"
    assert any("scientifically_reviewed_claim_allowed=true is forbidden" in e for e in errors)


def test_approved_report_missing_signature_fails(tmp_path: Path) -> None:
    root = _repo_root()
    for rel in REQUIRED_DOCS:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(root / rel, dest)
    for rel in (
        "policy/schemas/independent_review_report.v1.schema.json",
        "policy/schemas/independent_review_registry.v1.schema.json",
        "benchmarks/reviews/review_registry.v1.json",
        *REQUIRED_SLOTS,
    ):
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(root / rel, dest)

    slot = (
        tmp_path
        / "benchmarks"
        / "reviews"
        / "slots"
        / "laboratory_workflow_expert.UNSIGNED.json"
    )
    report = json.loads(slot.read_text(encoding="utf-8"))
    report["scope"] = {
        "scenario_plausibility": "reviewed_ok",
        "hazard_coverage": "reviewed_ok",
        "non_claims_language": "reviewed_ok",
    }
    report["findings_summary"] = "Looks plausible as simulation framing."
    report["checklist_completed"] = True
    report["approval"] = {
        "status": "approved",
        "signed": True,
        "reviewer_name": "Test Reviewer",
        "reviewer_affiliation": "Test Lab",
        "reviewed_at": "2026-07-25",
        "signature_ref": None,
        "attestation": "Approved without signature_ref (invalid).",
        "conflicts_of_interest_disclosed": True,
    }
    slot.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    errors = validate_independent_review_gate(tmp_path)
    assert any("signature_ref" in e for e in errors)


def test_charter_linked_from_golden_governance() -> None:
    text = (_repo_root() / "docs" / "benchmarks" / "golden_suite_governance.md").read_text(
        encoding="utf-8"
    )
    assert "docs/reviews/charter.md" in text or "reviews/charter" in text


def test_scientific_credibility_marks_pr8_materials() -> None:
    text = (_repo_root() / "docs" / "benchmarks" / "scientific_credibility.md").read_text(
        encoding="utf-8"
    )
    assert "LTG-PR8" in text
    assert "docs/reviews/" in text or "reviews/charter" in text
    assert "UNSIGNED" in text or "unsigned" in text.lower()
