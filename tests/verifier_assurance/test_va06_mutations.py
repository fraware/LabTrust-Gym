"""LT-VA-06 mutation immutability tests."""

from __future__ import annotations

import pytest

from labtrust_gym.verifier_assurance.mutations.profiles import (
    MutationError,
    apply_mutation_to_state,
    enforce_production_prohibition_for_release,
    map_risk_injector_to_mutation,
    validate_mutation_profile,
)


def _profile(**overrides):
    base = {
        "schema_id": "MutationProfile.v1",
        "mutation_id": "mut-test",
        "source_profile_id": "envprof-hospital-lab-v1",
        "target": "env",
        "dimension": "qc_drift",
        "operations": [{"op": "qc_drift", "device_id": "D1"}],
        "rationale": "test",
        "expected_effect": "qc fail",
        "production_prohibition": True,
        "claim_boundary": "simulation_research_only_no_clinical_validation",
    }
    base.update(overrides)
    return base


def test_unsupported_mutation_fail_closed() -> None:
    with pytest.raises(MutationError):
        validate_mutation_profile(_profile(dimension="not_a_real_dimension"))
    with pytest.raises(MutationError):
        apply_mutation_to_state({}, _profile(operations=[{"op": "unknown_op"}]))


def test_digest_immutability() -> None:
    p = validate_mutation_profile(_profile())
    tampered = dict(p)
    tampered["rationale"] = "changed"
    # Keep old digest
    with pytest.raises(MutationError):
        validate_mutation_profile(tampered)


def test_production_prohibition_enforcement() -> None:
    ok = validate_mutation_profile(_profile())
    enforce_production_prohibition_for_release([ok], release_export=True)
    bad = validate_mutation_profile(_profile(production_prohibition=True))
    # Flip flag after validation by rebuilding without prohibition
    with pytest.raises(MutationError):
        enforce_production_prohibition_for_release(
            [_profile(production_prohibition=False)],
            release_export=True,
        )
    mapped = map_risk_injector_to_mutation(
        "spoof_agent",
        source_profile_id="envprof-hospital-lab-v1",
        rationale="map injector",
        expected_effect="spoof blocked",
    )
    assert mapped["production_prohibition"] is True
    assert "mutation_digest" in mapped
    assert bad["mutation_digest"]
