"""LT-VA-08 campaign export and reconstruction tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from labtrust_gym.policy.loader import load_effective_policy
from labtrust_gym.verifier_assurance.campaign.export import (
    CampaignExportError,
    export_campaign_pack,
    reconstruct_campaign,
    validate_campaign_pack,
)
from labtrust_gym.verifier_assurance.environment_profile import hospital_lab_seed_profile
from labtrust_gym.verifier_assurance.oracle.dual_oracle import (
    default_hidden_profile,
    default_public_profile,
    make_inprocess_boundary,
)
from labtrust_gym.verifier_assurance.reward.composition import (
    build_reward_evidence_envelope,
    legacy_compat_policy,
)


def _base_pack_args(tmp_path: Path, env_profile: dict, commit: dict) -> dict:
    policy = legacy_compat_policy()
    comps = {c: 0.0 for c in policy["components"]}
    comps["operational_success"] = 1.0
    envelope = build_reward_evidence_envelope(
        envelope_id="ree-test-0000",
        run_id="camp-test",
        step=0,
        agent_id="attacker_0",
        policy=policy,
        components=comps,
        scalar_reward=1.0,
        public_verifier_id=default_public_profile()["verifier_id"],
        public_decision="accept",
    )
    return dict(
        out_dir=tmp_path / "pack",
        campaign_id="camp-test",
        environment_profile=env_profile,
        verifier_profiles=[default_public_profile(), default_hidden_profile()],
        trajectories=[{"steps": []}],
        snapshots=[{"schema_id": "CanonicalSnapshot.v1"}],
        reward_evidence=[envelope],
        verifier_results=[{"accepted": True}],
        commitments=[commit],
        exploit_manifests=[{"family": "qc_bypass"}],
        counterfactual_branches=[],
        mutation_profiles=[
            {
                "schema_id": "MutationProfile.v1",
                "mutation_id": "mut-1",
                "source_profile_id": env_profile["profile_id"],
                "target": "env",
                "dimension": "qc_drift",
                "operations": [{"op": "qc_drift", "device_id": "D1"}],
                "rationale": "r",
                "expected_effect": "e",
                "production_prohibition": True,
                "claim_boundary": "simulation_research_only_no_clinical_validation",
            }
        ],
    )


def test_campaign_pack_validation_and_hidden_exclusion(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    _p, fp, _pid, cal = load_effective_policy(repo)
    env_profile = hospital_lab_seed_profile(policy_fingerprint=fp, calibration_fingerprint=cal)
    boundary = make_inprocess_boundary("camp-test")
    state = {
        "result_released": True,
        "qc": {"results": {"R1": {"status": "released", "flags": []}}, "device_qc_state": {}},
        "process": {"invalid_process": True},
        "authorization": {},
        "audit": {},
        "critical": {},
        "side_effects": {},
    }
    commit = boundary.seal_episode(state, "ep1")
    args = _base_pack_args(tmp_path, env_profile, commit)
    pack_dir = Path(args.pop("out_dir"))
    export_campaign_pack(pack_dir, **args)
    result = validate_campaign_pack(pack_dir)
    assert result["valid"] is True
    reconstructed = reconstruct_campaign(pack_dir)
    assert reconstructed["campaign_id"] == "camp-test"
    for p in (pack_dir / "adjudications_or_commitments").glob("*.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        assert "adjudication" not in doc
        assert doc.get("revealed") is False
    assert any((pack_dir / "reward_evidence").glob("*.json"))


def test_campaign_reconstruction_checksum_mismatch(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    _p, fp, _pid, cal = load_effective_policy(repo)
    env_profile = hospital_lab_seed_profile(policy_fingerprint=fp, calibration_fingerprint=cal)
    boundary = make_inprocess_boundary("camp-bad")
    commit = boundary.seal_episode(
        {
            "result_released": True,
            "qc": {"results": {"R1": {"status": "released", "flags": []}}, "device_qc_state": {}},
            "process": {},
            "authorization": {},
            "audit": {},
            "critical": {},
            "side_effects": {},
        },
        "ep1",
    )
    args = _base_pack_args(tmp_path, env_profile, commit)
    pack_dir = Path(args.pop("out_dir"))
    export_campaign_pack(pack_dir, **args)
    target = next((pack_dir / "trajectories").glob("*.json"))
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(CampaignExportError, match="checksum mismatch"):
        validate_campaign_pack(pack_dir)


def test_campaign_reconstruction_missing_tree(tmp_path: Path) -> None:
    empty = tmp_path / "empty_pack"
    empty.mkdir()
    with pytest.raises(CampaignExportError, match="missing required path"):
        validate_campaign_pack(empty)


def test_campaign_rejects_revealed_adjudication_in_public_pack(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    _p, fp, _pid, cal = load_effective_policy(repo)
    env_profile = hospital_lab_seed_profile(policy_fingerprint=fp, calibration_fingerprint=cal)
    boundary = make_inprocess_boundary("camp-leak")
    state = {
        "result_released": True,
        "qc": {"results": {"R1": {"status": "released", "flags": []}}, "device_qc_state": {}},
        "process": {"invalid_process": True},
        "authorization": {},
        "audit": {},
        "critical": {},
        "side_effects": {},
    }
    boundary.seal_episode(state, "ep1")
    revealed = boundary.freeze_and_reveal()[0]
    args = _base_pack_args(tmp_path, env_profile, revealed)
    pack_dir = Path(args.pop("out_dir"))
    export_campaign_pack(pack_dir, **args)
    leak = next((pack_dir / "adjudications_or_commitments").glob("*.json"))
    doc = json.loads(leak.read_bytes().decode("utf-8"))
    doc["adjudication"] = {"accepted": False}
    doc["revealed"] = True
    leak.write_bytes((json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    release_path = pack_dir / "release_manifest.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    rel = f"adjudications_or_commitments/{leak.name}"
    release["checksums"][rel] = hashlib.sha256(leak.read_bytes()).hexdigest()
    release_path.write_bytes((json.dumps(release, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    with pytest.raises(CampaignExportError, match="hidden adjudication"):
        validate_campaign_pack(pack_dir)
