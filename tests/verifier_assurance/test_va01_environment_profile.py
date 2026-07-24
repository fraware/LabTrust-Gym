"""LT-VA-01 EnvironmentProfile tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from labtrust_gym.pcs.ids import CLAIM_ARTIFACT_ID, VERIFICATION_POLICY_ID
from labtrust_gym.policy.loader import load_effective_policy
from labtrust_gym.verifier_assurance.environment_profile import (
    EnvironmentProfileError,
    bind_pcs_identity_refs,
    compute_profile_digest,
    dump_environment_profile,
    hospital_lab_seed_profile,
    load_environment_profile,
    validate_environment_profile,
)

REPO = Path(__file__).resolve().parents[2]


def _seed() -> dict:
    _policy, fingerprint, _pid, cal_fp = load_effective_policy(REPO)
    return hospital_lab_seed_profile(
        policy_fingerprint=fingerprint,
        calibration_fingerprint=cal_fp,
        pcs_identity_refs=[CLAIM_ARTIFACT_ID, VERIFICATION_POLICY_ID],
    )


def test_digest_stability() -> None:
    a = _seed()
    b = _seed()
    assert a["profile_digest"] == b["profile_digest"]
    assert compute_profile_digest(a) == a["profile_digest"]


def test_unknown_field_reject() -> None:
    profile = _seed()
    profile["unexpected_field"] = "nope"
    profile.pop("profile_digest", None)
    with pytest.raises(EnvironmentProfileError):
        validate_environment_profile(profile)


def test_profile_round_trip(tmp_path: Path) -> None:
    profile = _seed()
    path = tmp_path / "env_profile.json"
    digest = dump_environment_profile(profile, path)
    loaded = load_environment_profile(path)
    assert loaded["profile_digest"] == digest
    assert loaded["environment_family"] == "hospital_lab"
    assert loaded["known_fidelity_limits"]


def test_missing_digest_fail_closed() -> None:
    profile = _seed()
    digests = dict(profile["policy_digests"])
    digests["policy_fingerprint"] = ""
    profile["policy_digests"] = digests
    profile.pop("profile_digest", None)
    with pytest.raises(EnvironmentProfileError):
        validate_environment_profile(profile)


def test_pcs_identity_binding() -> None:
    profile = _seed()
    bound = bind_pcs_identity_refs(profile, [CLAIM_ARTIFACT_ID, VERIFICATION_POLICY_ID])
    assert CLAIM_ARTIFACT_ID in bound["policy_digests"]["pcs_identity_refs"]
    # Mutating digest after bind must fail closed
    tampered = copy.deepcopy(bound)
    tampered["profile_digest"] = "deadbeef" * 8
    with pytest.raises(EnvironmentProfileError):
        validate_environment_profile(tampered)


def test_seed_fixture_written() -> None:
    """Ensure benchmark fixture exists and validates."""
    fixture = REPO / "benchmarks" / "verifier_assurance" / "fixtures" / "environment_profile.hospital_lab.v1.json"
    if not fixture.exists():
        profile = _seed()
        dump_environment_profile(profile, fixture)
    loaded = load_environment_profile(fixture)
    assert loaded["schema_id"] == "EnvironmentProfile.v1"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert data["claim_boundary"] == "simulation_research_only_no_clinical_validation"
