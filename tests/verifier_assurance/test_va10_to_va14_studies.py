"""LT-VA-10..14 study and release tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.verifier_assurance.calibration.aggregate import (
    CalibrationAdapterError,
    build_va_release_pack,
    compare_simulated_vs_aggregate,
    validate_aggregate_only,
)
from labtrust_gym.verifier_assurance.campaign.export import reconstruct_campaign
from labtrust_gym.verifier_assurance.oracle.dual_oracle import PublicVerifier, default_public_profile
from labtrust_gym.verifier_assurance.studies.authorization import (
    LocalFakePFCoreChecker,
    PFCoreAdapter,
    TracePredicateInput,
    run_authorization_campaign,
)
from labtrust_gym.verifier_assurance.studies.coevolution import run_coevolution_campaign
from labtrust_gym.verifier_assurance.studies.outcome_process import run_outcome_process_study
from labtrust_gym.verifier_assurance.studies.responsibility import run_responsibility_campaign
from labtrust_gym.verifier_assurance.training.offline_ppo import (
    OfflinePPOConfig,
    train_policy_against_public,
)


def test_va12_attribution_branches() -> None:
    result = run_responsibility_campaign()
    assert len(result["cases"]) == 6
    assert "legal" in result["non_legal_disclaimer"].lower()
    assert result["metrics"]["attribution_precision"] == 1.0
    assert result["metrics"]["attribution_recall"] == 1.0
    assert "parent_snapshot" in result
    assert result["parent_snapshot"]["schema_id"] == "CanonicalSnapshot.v1"
    assert result["cases"][0]["branch_records"]


def test_va11_authorization_campaign() -> None:
    result = run_authorization_campaign()
    assert result["study_id"] == "VA-11"
    assert len(result["results"]) >= 10
    assert all(r["attack_hidden_accepted"] is False for r in result["results"])
    assert result["metrics"]["public_false_accept_count"] >= 1
    assert result["pf_core_checker"] == "local_fake_pf_core"
    assert all(r["pf_core"]["status"] == "fail" for r in result["results"])
    assert all(r["pf_core"]["checker"] == "local_fake_pf_core" for r in result["results"])


def test_va10_recovers_at_least_three_exploit_families() -> None:
    result = run_outcome_process_study()
    assert result["recovered_count"] >= 3
    families = {e["family"] for e in result["recovered_exploit_families"]}
    assert len(families) >= 3
    assert result["metrics"]["v_public_false_accept_rate"] > 0


def test_va11_pf_core_unavailable_is_indeterminate_not_pass() -> None:
    adapter = PFCoreAdapter(allow_local_fake=False)
    # Without real pf_core installed this is indeterminate; never pass.
    if adapter.available:
        pytest.skip("pf_core unexpectedly installed in this environment")
    out = adapter.check_trace_predicates({"authorization": {"unauthorized": True}})
    assert out["status"] == "indeterminate"
    assert out["reason"] == "pf_core_unavailable"


def test_va11_local_fake_pf_typed_contract() -> None:
    checker = LocalFakePFCoreChecker()
    clean = TracePredicateInput.from_trace(
        {"authorization": {}, "process": {}, "audit": {}},
        trace_id="clean",
    )
    assert checker.check(clean).status == "pass"
    dirty = TracePredicateInput.from_trace(
        {"authorization": {"unauthorized": True}, "process": {}, "audit": {}},
        trace_id="dirty",
    )
    assert checker.check(dirty).status == "fail"
    unknown = TracePredicateInput(
        trace_id="u",
        authorization={},
        process={},
        audit={},
        predicates=("not_a_real_predicate",),
    )
    assert checker.check(unknown).status == "indeterminate"


def test_va13_coevolution_fresh_attacker(tmp_path: Path) -> None:
    result = run_coevolution_campaign(checkpoint_dir=tmp_path / "ckpts", episodes=12, seed=7)
    assert result["acceptance"]["policy_trained_against_v_public"] is True
    assert result["acceptance"]["fresh_policy_attacked_repaired"] is True
    assert result["post_repair_original_policy"]["public_accepted"] is False
    assert result["policy_trained_against_public"]["trained_against"] == "V_public.hospital_lab.v1"
    assert result["acceptance"]["training_backend"] == "numpy_ppo"
    assert len(result["acceptance"]["frozen_checkpoint_ids"]) == 2
    assert result["checkpoints"]["v1"]["checkpoint_id"].startswith("ckpt-")
    assert result["metrics"]["exploit_migration"] is True


def test_va13_offline_ppo_deterministic(tmp_path: Path) -> None:
    pub = PublicVerifier(default_public_profile())
    cfg = OfflinePPOConfig(seed=123, episodes=6, horizon=3, checkpoint_dir=tmp_path)
    a = train_policy_against_public(pub, policy_id="det-a", config=cfg)
    b = train_policy_against_public(pub, policy_id="det-a", config=cfg)
    assert a.checkpoint.logits_digest == b.checkpoint.logits_digest
    assert a.checkpoint.checkpoint_id == b.checkpoint.checkpoint_id
    assert a.checkpoint.mean_public_reward == b.checkpoint.mean_public_reward


def test_va14_calibration_forbids_raw_and_builds_release(tmp_path: Path) -> None:
    with pytest.raises(CalibrationAdapterError):
        validate_aggregate_only({"patient_id": "x"})
    cmp = compare_simulated_vs_aggregate(
        {"stat_rate": 0.1, "arrival_mean_s": 50.0},
        {"stat_rate": 0.12, "arrival_mean_s": 50.0},
    )
    assert cmp["schema_id"] == "AggregateCalibrationComparison.v1"
    pack_dir = tmp_path / "va_release"
    pack = build_va_release_pack(pack_dir)
    assert pack["campaign_id"] == "labtrust-va-release-v1"
    reconstructed = reconstruct_campaign(pack_dir)
    assert reconstructed["valid"] is True
    ree = list((pack_dir / "reward_evidence").glob("*.json"))
    assert len(ree) >= 1
    bench = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "verifier_assurance"
        / "release_packs"
        / "labtrust-va-release-v1"
    )
    if not (bench / "release_manifest.json").exists():
        build_va_release_pack(bench)
    assert reconstruct_campaign(bench)["valid"] is True
