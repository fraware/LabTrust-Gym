"""LTG-PR9 benchmark release DoD smoke (CI-friendly).

Checks packaging identity, non-claims posture, review gate, pin, and
reconstruction imports. Skips heavy reproduce / full pack by default.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.policy.independent_review import (
    scientifically_reviewed_claim_allowed,
    validate_independent_review_gate,
)
from labtrust_gym.policy.validate import validate_policy

CANDIDATE_REL = "benchmarks/releases/labtrust-benchmark-v0.2-candidate"
MANIFEST_REL = f"{CANDIDATE_REL}/release_manifest.json"
PIN_REL = "benchmarks/external_integrations/pinned_release.v1.json"

REQUIRED_DOCS = (
    "docs/benchmarks/scientific_credibility.md",
    "docs/benchmarks/release_runbook.md",
    "docs/benchmarks/non_claims_freeze.md",
    "docs/reviews/signed_approval_gate.md",
    "docs/verifier_assurance/non_claims.md",
    f"{CANDIDATE_REL}/NOTES.md",
    "benchmarks/releases/README.md",
)

REQUIRED_IMPORTS = (
    ("labtrust_gym.export.reconstruction", "build_reconstruction_block"),
    ("labtrust_gym.export.reconstruction", "build_pack_reconstruction"),
    ("labtrust_gym.export.receipts", "write_evidence_bundle"),
    ("labtrust_gym.export.verify", "verify_bundle"),
    ("labtrust_gym.policy.independent_review", "assert_scientifically_reviewed_claim_allowed"),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_key_release_docs_exist() -> None:
    root = _repo_root()
    for rel in REQUIRED_DOCS:
        assert (root / rel).is_file(), f"missing required doc: {rel}"


def test_validate_policy_api_green() -> None:
    errors = validate_policy(_repo_root())
    assert errors == [], errors


def test_independent_review_gate_green_claim_disallowed() -> None:
    root = _repo_root()
    errors = validate_independent_review_gate(root)
    assert errors == [], errors
    assert scientifically_reviewed_claim_allowed(root) is False


def test_external_integrations_pin_present_and_consistent() -> None:
    root = _repo_root()
    pin_path = root / PIN_REL
    assert pin_path.is_file(), PIN_REL
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    assert pin.get("no_live_llm") is True
    baselines = pin.get("baselines_pack") or {}
    assert (root / str(baselines.get("path") or "")).is_dir()
    va = pin.get("va_release_pack") or {}
    assert (root / str(va.get("path") or "")).is_dir()


def test_reconstruction_and_export_helpers_importable() -> None:
    import importlib

    for module_name, attr in REQUIRED_IMPORTS:
        mod = importlib.import_module(module_name)
        assert hasattr(mod, attr), f"{module_name}.{attr} missing"


def test_candidate_release_manifest_posture() -> None:
    root = _repo_root()
    path = root / MANIFEST_REL
    assert path.is_file(), MANIFEST_REL
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("schema_id") == "LabTrustBenchmarkReleaseCandidate.v1"
    assert data.get("release_id") == "labtrust-benchmark-v0.2-candidate"
    assert data.get("scientifically_reviewed") is False
    assert data.get("scientifically_reviewed_claim_allowed") is False
    assert data.get("claim_posture") == "engineering_benchmark_only"
    assert data.get("non_claims_ref") == "docs/benchmarks/non_claims_freeze.md"
    pins = data.get("pins") or {}
    assert pins.get("external_integrations") == PIN_REL
    assert (root / PIN_REL).is_file()
    assert (root / str(pins.get("independent_review_registry") or "")).is_file()
    baselines = pins.get("official_baselines") or {}
    assert (root / str(baselines.get("path") or "")).is_dir()
    va = pins.get("va_release_pack") or {}
    assert (root / str(va.get("path") or "")).is_dir()
    gaps = data.get("known_gaps") or []
    gap_ids = {g.get("id") for g in gaps if isinstance(g, dict)}
    assert "catalog_drift" in gap_ids
    assert "unsigned_independent_reviews" in gap_ids
    freeze = (root / "docs/benchmarks/non_claims_freeze.md").read_text(encoding="utf-8").lower()
    for marker in ("clinical validation", "deployment", "scientifically reviewed"):
        assert marker in freeze


def test_non_claims_freeze_has_no_clinical_endorsement() -> None:
    root = _repo_root()
    text = (root / "docs/benchmarks/non_claims_freeze.md").read_text(encoding="utf-8").lower()
    forbidden = (
        "clinically validated laboratory",
        "approved for clinical use",
        "deployment-ready medical",
    )
    for phrase in forbidden:
        assert phrase not in text, f"forbidden endorsement language: {phrase!r}"


@pytest.mark.skipif(
    __import__("os").environ.get("LABTRUST_LTG_RELEASE_FULL") != "1",
    reason="Full release path is manual; set LABTRUST_LTG_RELEASE_FULL=1 to opt in",
)
def test_optional_full_release_marker_documented() -> None:
    """Placeholder opt-in for maintainers running the full runbook locally."""
    runbook = (_repo_root() / "docs/benchmarks/release_runbook.md").read_text(encoding="utf-8")
    assert "labtrust reproduce --profile minimal" in runbook
    assert "labtrust verify-release" in runbook
