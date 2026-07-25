"""LT-VA-15 sealed holdouts and LTG-05 gap exploit families."""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.verifier_assurance.holdouts.partition import (
    HoldoutPartitionError,
    assert_no_holdout_leakage,
    build_partition_manifest,
    filter_public_pack_records,
    load_partition_manifest,
    seal_eval_holdout,
    split_train_eval,
    verify_eval_commitment,
)
from labtrust_gym.verifier_assurance.studies.holdout_exploits import (
    HOLDOUT_EXPLOIT_FAMILIES,
    run_holdout_exploit_study,
    run_partitioned_holdout_campaign,
    seed_holdout_exploit_state,
)
from labtrust_gym.verifier_assurance.studies.outcome_process import run_outcome_process_study

REPO = Path(__file__).resolve().parents[2]
FIXTURE = (
    REPO
    / "benchmarks"
    / "verifier_assurance"
    / "fixtures"
    / "holdout_partition.hospital_lab.v1.json"
)


def test_split_train_eval_deterministic_and_disjoint() -> None:
    a_train, a_eval = split_train_eval([f"e{i}" for i in range(10)], train_ratio=0.7, seed=3)
    b_train, b_eval = split_train_eval([f"e{i}" for i in range(10)], train_ratio=0.7, seed=3)
    assert a_train == b_train and a_eval == b_eval
    assert set(a_train).isdisjoint(a_eval)
    assert len(a_train) + len(a_eval) == 10
    assert a_eval  # never empty for n>=2


def test_build_and_verify_eval_commitment() -> None:
    salt = bytes.fromhex("ab" * 32)
    manifest = build_partition_manifest(
        partition_id="test-partition",
        campaign_id="test-campaign",
        train_episode_ids=["train_a", "train_b"],
        eval_episode_ids=["eval_x", "eval_y"],
        salt=salt,
    )
    assert manifest["eval"]["sealed"] is True
    assert verify_eval_commitment(
        manifest["commitments"],
        eval_episode_ids=["eval_x", "eval_y"],
        campaign_id="test-campaign",
    )
    # Wrong membership fails verification
    assert not verify_eval_commitment(
        manifest["commitments"],
        eval_episode_ids=["eval_x", "eval_z"],
        campaign_id="test-campaign",
    )


def test_train_eval_overlap_fail_closed() -> None:
    with pytest.raises(HoldoutPartitionError, match="overlap"):
        build_partition_manifest(
            partition_id="bad",
            campaign_id="bad",
            train_episode_ids=["shared"],
            eval_episode_ids=["shared"],
            salt=bytes.fromhex("cd" * 32),
        )


def test_public_pack_filters_eval_and_detects_leakage() -> None:
    salt = bytes.fromhex("ef" * 32)
    manifest = build_partition_manifest(
        partition_id="leak-test",
        campaign_id="leak-campaign",
        train_episode_ids=["train_1"],
        eval_episode_ids=["eval_secret"],
        salt=salt,
    )
    records = [
        {"episode_id": "train_1", "trajectory": {"ok": True}},
        {"episode_id": "eval_secret", "trajectory": {"secret": True}},
        {
            "episode_id": "eval_secret",
            "commitment_only": True,
            "partition": "eval_holdout",
            "commitment": "abc",
        },
    ]
    public = filter_public_pack_records(records, manifest)
    ids = {r["episode_id"] for r in public}
    assert "train_1" in ids
    assert any(r.get("commitment_only") for r in public)
    # Full eval trajectory excluded
    assert not any(r.get("trajectory", {}).get("secret") for r in public)

    assert_no_holdout_leakage({"records": public, "public_pack": True}, manifest)

    with pytest.raises(HoldoutPartitionError, match="leaked"):
        assert_no_holdout_leakage(
            {"episode_id": "eval_secret", "trajectory": {"x": 1}},
            manifest,
        )


def test_fixture_manifest_loads() -> None:
    manifest = load_partition_manifest(FIXTURE)
    assert manifest["schema_id"] == "HoldoutPartitionManifest.v1"
    assert len(manifest["eval"]["episode_ids"]) == 5
    assert set(manifest["eval"]["exploit_families"]) == set(HOLDOUT_EXPLOIT_FAMILIES)


def test_va15_recovers_holdout_families() -> None:
    result = run_holdout_exploit_study()
    assert result["study_id"] == "VA-15"
    assert result["recovered_count"] >= 4
    families = {e["family"] for e in result["recovered_exploit_families"]}
    for required in (
        "sparse_reward_exploitation",
        "delayed_safety_failure",
        "proxy_metric_gaming",
        "selective_evidence_omission",
    ):
        assert required in families
    assert "attack_transfer_across_seeds" in families
    transfer = next(e for e in result["recovered_exploit_families"] if e["family"] == "attack_transfer_across_seeds")
    assert transfer["transfer_rate"] >= 0.6
    assert len(transfer["seeds_recovered"]) >= 3


def test_va15_partitioned_campaign_no_public_leakage() -> None:
    out = run_partitioned_holdout_campaign()
    public = out["public_pack"]
    manifest = out["partition_manifest"]
    assert_no_holdout_leakage(public, manifest, path="public")
    eval_ids = set(manifest["eval"]["episode_ids"])
    for rec in public["records"]:
        if rec.get("commitment_only"):
            assert rec["partition"] == "eval_holdout"
            assert rec["episode_id"] in eval_ids
        else:
            assert rec["episode_id"] not in eval_ids or rec.get("partition") != "eval"
    assert out["study"]["recovered_count"] >= 4


def test_va10_still_recovers_process_outcome_families() -> None:
    # Regression: extended hidden profile must not break VA-10.
    result = run_outcome_process_study()
    assert result["recovered_count"] >= 3


def test_holdout_seed_states_are_offline_fixtures() -> None:
    for family in HOLDOUT_EXPLOIT_FAMILIES:
        state = seed_holdout_exploit_state(family, seed=0)
        assert state["result_released"] is True
        assert "hidden_adjudication" not in state


def test_seal_eval_holdout_stable_with_fixed_salt() -> None:
    c1 = seal_eval_holdout(["b", "a"], campaign_id="c", salt=b"\x01" * 32)
    c2 = seal_eval_holdout(["a", "b"], campaign_id="c", salt=b"\x01" * 32)
    assert c1["eval_set_commitment"] == c2["eval_set_commitment"]
