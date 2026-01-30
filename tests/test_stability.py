"""
Stability policy and START_RUN gating.

- engine/catalogue_runtime.py: panel lookup, stability limits, check_stability,
  check_temp_out_of_band.
- START_RUN: if now - collection/separated > max_age => BLOCKED TIME_EXPIRED
  unless OVERRIDE_RISK_ACCEPTANCE token; temp out-of-band => BLOCKED TEMP_OUT_OF_BAND.
- CENTRIFUGE_END updates separated_ts_s; ALIQUOT_CREATE records aliquot -> specimen.
- START_RUN_OVERRIDE with token consumes token and allows run.
- GS-001, GS-006, GS-007 pass when LABTRUST_RUN_GOLDEN=1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.engine.catalogue_runtime import (
    check_stability,
    check_temp_out_of_band,
    get_stability_limits_for_panel,
    load_stability_policy,
)
from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.engine.specimens import SpecimenStore
from labtrust_gym.runner import GoldenRunner


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---- catalogue_runtime unit tests ----
def test_stability_limits_biochem() -> None:
    policy = load_stability_policy(
        _repo_root() / "policy" / "stability" / "stability_policy.v0.1.yaml"
    )
    limits = get_stability_limits_for_panel(policy, "BIOCHEM_PANEL_CORE")
    assert limits["pre_separation_max_s"] == 120 * 60
    assert limits["post_separation_ambient_max_s"] == 360 * 60


def test_check_stability_pass() -> None:
    policy = {}
    ok, viol, reason, pass_inv = check_stability(
        collection_ts_s=0,
        separated_ts_s=1370,
        now_s=1500,
        panel_id="BIOCHEM_PANEL_CORE",
        stability_policy=policy,
    )
    assert ok is True
    assert pass_inv == "INV-STAB-BIOCHEM-001"


def test_check_stability_expired() -> None:
    policy = {}
    ok, viol, reason, pass_inv = check_stability(
        collection_ts_s=0,
        separated_ts_s=42000,
        now_s=42010,
        panel_id="BIOCHEM_PANEL_CORE",
        stability_policy=policy,
    )
    assert ok is False
    assert viol == "INV-STAB-BIOCHEM-002"
    assert reason == "TIME_EXPIRED"


def test_check_temp_out_of_band() -> None:
    assert check_temp_out_of_band(
        "REFRIGERATED_2_8",
        [{"t_s": 4000, "temp_band": "AMBIENT_20_25"}],
    ) is True
    assert check_temp_out_of_band(None, []) is False


def test_specimen_separated_ts_and_aliquot() -> None:
    store = SpecimenStore()
    store.load_initial([{"specimen_id": "S1", "panel_id": "BIOCHEM_PANEL_CORE", "collection_ts_s": 0, "arrival_ts_s": 600, "separated_ts_s": None}])
    store.set_separated_ts("S1", 1370)
    assert store.get("S1").get("separated_ts_s") == 1370
    store.record_aliquot("A1", "S1")
    assert store.resolve_to_specimen_ids(aliquot_ids=["A1"]) == ["S1"]


# ---- CoreEnv GS-001, GS-006, GS-007 ----
def _should_run_golden() -> bool:
    return os.environ.get("LABTRUST_RUN_GOLDEN") == "1"


GS001_SCRIPT = [
    {"event_id": "e1", "t_s": 600, "agent_id": "A_RECEPTION", "action_type": "CREATE_ACCESSION", "args": {"specimen_id": "S1"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["CREATE_ACCESSION"]}},
    {"event_id": "e2", "t_s": 610, "agent_id": "A_RECEPTION", "action_type": "CHECK_ACCEPTANCE_RULES", "args": {"specimen_id": "S1"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["CHECK_ACCEPTANCE_RULES"]}},
    {"event_id": "e3", "t_s": 620, "agent_id": "A_RECEPTION", "action_type": "ACCEPT_SPECIMEN", "args": {"specimen_id": "S1"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["ACCEPT_SPECIMEN"]}},
    {"event_id": "e4", "t_s": 700, "agent_id": "A_PREAN", "action_type": "MOVE", "args": {"entity_type": "Specimen", "entity_id": "S1", "from_zone": "Z_SORTING_LANES", "to_zone": "Z_CENTRIFUGE_BAY"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["MOVE"]}},
    {"event_id": "e5", "t_s": 710, "agent_id": "A_PREAN", "action_type": "CENTRIFUGE_START", "args": {"device_id": "DEV_CENTRIFUGE_BANK_01", "specimen_ids": ["S1"]}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["CENTRIFUGE_START"]}},
    {"event_id": "e6", "t_s": 1370, "agent_id": "A_PREAN", "action_type": "CENTRIFUGE_END", "args": {"device_id": "DEV_CENTRIFUGE_BANK_01", "specimen_ids": ["S1"], "separated_ts_s": 1370}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["CENTRIFUGE_END"]}},
    {"event_id": "e7", "t_s": 1400, "agent_id": "A_PREAN", "action_type": "ALIQUOT_CREATE", "args": {"device_id": "DEV_ALIQUOTER_01", "specimen_id": "S1", "aliquot_id": "A1"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["ALIQUOT_CREATE"]}},
    {"event_id": "e8", "t_s": 1450, "agent_id": "A_ANALYTICS", "action_type": "QUEUE_RUN", "args": {"device_id": "DEV_CHEM_A_01", "aliquot_ids": ["A1"]}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["QUEUE_RUN"]}},
    {"event_id": "e9", "t_s": 1500, "agent_id": "A_ANALYTICS", "action_type": "START_RUN", "args": {"device_id": "DEV_CHEM_A_01", "run_id": "R1", "aliquot_ids": ["A1"]}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["START_RUN"], "violations": ["INV-STAB-BIOCHEM-001:PASS"]}},
]

GS001 = {
    "scenario_id": "GS-001",
    "title": "Happy path: routine BIOCHEM_PANEL_CORE end-to-end",
    "initial_state": {
        "system": {},
        "agents": [{"agent_id": "A_PREAN", "zone_id": "Z_CENTRIFUGE_BAY"}],
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [],
    },
    "script": GS001_SCRIPT,
}

GS006 = {
    "scenario_id": "GS-006",
    "title": "Stability expired BIOCHEM requires OVERRIDE_RISK_ACCEPTANCE dual approval",
    "initial_state": {
        "system": {},
        "specimens": [
            {
                "specimen_id": "S4",
                "patient_identifiers_hash": "pid:hash:004",
                "collection_ts_s": 0,
                "arrival_ts_s": 40000,
                "panel_id": "BIOCHEM_PANEL_CORE",
                "container_type": "SERUM_SST",
                "specimen_type": "SERUM",
                "integrity_flags": {"leak": False, "clot": False, "hemolysis": False, "insufficient_volume": False, "label_issue": False},
                "separated_ts_s": 42000,
                "temp_band": "AMBIENT_20_25",
                "status": "accepted",
            }
        ],
        "tokens": [],
    },
    "script": [
        {"event_id": "e1", "t_s": 42010, "agent_id": "A_ANALYTICS", "action_type": "START_RUN", "args": {"device_id": "DEV_CHEM_A_01", "run_id": "R4", "specimen_ids": ["S4"]}, "reason_code": None, "token_refs": [], "expect": {"status": "BLOCKED", "violations": ["INV-STAB-BIOCHEM-002:VIOLATION"], "blocked_reason_code": "TIME_EXPIRED"}},
        {"event_id": "e2", "t_s": 42020, "agent_id": "A_SUPERVISOR", "action_type": "MINT_TOKEN", "args": {"token_type": "OVERRIDE_RISK_ACCEPTANCE", "subject_type": "specimen", "subject_id": "S4", "reason_code": "TIME_EXPIRED", "approvals": ["A_SUPERVISOR"]}, "reason_code": "TIME_EXPIRED", "token_refs": [], "expect": {"status": "BLOCKED", "violations": ["INV-TOK-001:VIOLATION"]}},
        {"event_id": "e3", "t_s": 42030, "agent_id": "A_SUPERVISOR", "action_type": "MINT_TOKEN", "args": {"token_type": "OVERRIDE_RISK_ACCEPTANCE", "subject_type": "specimen", "subject_id": "S4", "reason_code": "TIME_EXPIRED", "approvals": [{"approver_agent_id": "A_SUPERVISOR", "approver_key_id": "ed25519:key_supervisor"}, {"approver_agent_id": "A_CLINSCI", "approver_key_id": "ed25519:key_clinsci"}]}, "reason_code": "TIME_EXPIRED", "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["MINT_TOKEN"]}},
        {"event_id": "e4", "t_s": 42040, "agent_id": "A_ANALYTICS", "action_type": "START_RUN_OVERRIDE", "args": {"device_id": "DEV_CHEM_A_01", "run_id": "R4", "specimen_ids": ["S4"], "reason_code": "TIME_EXPIRED"}, "reason_code": "TIME_EXPIRED", "token_refs": ["T_OVR_S4"], "expect": {"status": "ACCEPTED", "emits": ["START_RUN"], "violations": ["INV-TOK-003:PASS"], "token_consumed": ["T_OVR_S4"]}},
    ],
}

GS007 = {
    "scenario_id": "GS-007",
    "title": "Temp out-of-band requires OVERRIDE_RISK_ACCEPTANCE; without token blocked",
    "initial_state": {
        "system": {},
        "agents": [{"agent_id": "A_ANALYTICS", "zone_id": "Z_ANALYZER_HALL_B"}],
        "specimens": [
            {
                "specimen_id": "S5",
                "patient_identifiers_hash": "pid:hash:005",
                "collection_ts_s": 0,
                "arrival_ts_s": 600,
                "panel_id": "COAG_PANEL_CORE",
                "container_type": "PLASMA_CITRATE",
                "specimen_type": "PLASMA",
                "fill_ratio_ok": True,
                "separated_ts_s": 700,
                "temp_band": "AMBIENT_20_25",
                "storage_requirement": "REFRIGERATED_2_8",
                "temp_exposure_log": [{"t_s": 700, "temp_band": "AMBIENT_20_25"}, {"t_s": 4000, "temp_band": "AMBIENT_20_25"}],
                "status": "accepted",
            }
        ],
        "tokens": [],
    },
    "script": [
        {"event_id": "e1", "t_s": 4010, "agent_id": "A_ANALYTICS", "action_type": "START_RUN", "args": {"device_id": "DEV_COAG_01", "run_id": "R5", "specimen_ids": ["S5"]}, "reason_code": None, "token_refs": [], "expect": {"status": "BLOCKED", "blocked_reason_code": "TEMP_OUT_OF_BAND", "violations": ["INV-ZONE-006:VIOLATION"]}},
    ],
}


@pytest.mark.parametrize("scenario", [GS001, GS006, GS007], ids=["GS-001", "GS-006", "GS-007"])
def test_gs001_gs006_gs007(scenario: dict) -> None:
    """Run GS-001, GS-006, GS-007 with CoreEnv. Skipped unless LABTRUST_RUN_GOLDEN=1."""
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run stability scenarios.")
    root = _repo_root()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        pytest.fail("Emits vocab not found")
    env = CoreEnv()
    runner = GoldenRunner(env, emits_vocab_path=str(emits_path))
    report = runner._run_scenario(scenario, rng_seed=12345)
    assert report.passed, f"Scenario {scenario['scenario_id']} failed: {report.failures}"
