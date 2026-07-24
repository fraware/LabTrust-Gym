"""Existence checks for LT-VA-00 baseline and preregistration artifacts."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_baseline_freeze_exists_and_records_commit() -> None:
    path = REPO / "docs" / "verifier_assurance" / "baseline_freeze.md"
    text = path.read_text(encoding="utf-8")
    assert "1d9f2fa0b853975cb4a215f7a32eb3015356c3cd" in text
    assert "simulation and research" in text.lower() or "simulation and research" in text
    assert "clinical" in text.lower()


def test_adrs_exist() -> None:
    adr = REPO / "docs" / "adr"
    assert (adr / "ADR-VA-001-dual-oracle-architecture.md").is_file()
    assert (adr / "ADR-VA-002-claim-boundaries.md").is_file()
    assert (adr / "ADR-VA-003-grant-semantics.md").is_file()


def test_preregistration_before_results() -> None:
    path = REPO / "docs" / "verifier_assurance" / "experiment_preregistration.md"
    text = path.read_text(encoding="utf-8")
    assert "before results exist" in text.lower()
    assert "VA-10" in text and "VA-13" in text
    assert "≥3" in text or ">=3" in text


def test_threat_model_extension() -> None:
    text = (REPO / "docs" / "architecture" / "threat_model.md").read_text(encoding="utf-8")
    assert "Optimization-induced verifier failure" in text
    assert "Label leakage" in text
    assert "Authorization attack surfaces" in text


def test_non_claims_doc() -> None:
    text = (REPO / "docs" / "verifier_assurance" / "non_claims.md").read_text(encoding="utf-8")
    assert "does **not**" in text or "does not" in text.lower()
    assert "production clinical" in text.lower() or "clinical assurance" in text.lower()
