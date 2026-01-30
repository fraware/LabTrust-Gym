"""
Critical results classification and mandatory notify/ack record.

- engine/critical.py: classify CRIT_A/CRIT_B/none, comm records, has_ack.
- RELEASE_RESULT blocked until ACK recorded (CRIT_NO_ACK, INV-CRIT-002).
- Downtime: auto NOTIFY_CRITICAL_RESULT on generate, notification_mode_required.
- query: result_criticality, comm_record_exists, notification_mode_required.
- GS-016, GS-017, GS-018 pass when LABTRUST_RUN_GOLDEN=1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.engine.critical import (
    CriticalStore,
    classify_criticality,
    default_thresholds,
)
from labtrust_gym.runner import GoldenRunner


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---- engine/critical.py unit tests ----
def test_classify_criticality_k_high() -> None:
    th = default_thresholds()
    assert classify_criticality("BIOCHEM_POTASSIUM_K", 7.0, "mmol/L", th) == "CRIT_A"
    assert classify_criticality("BIOCHEM_POTASSIUM_K", 4.0, "mmol/L", th) == "none"


def test_classify_criticality_na_high() -> None:
    th = default_thresholds()
    assert classify_criticality("BIOCHEM_SODIUM_NA", 165.0, "mmol/L", th) == "CRIT_A"


def test_critical_store_ack_gating() -> None:
    store = CriticalStore()
    store.load_thresholds(default_thresholds())
    store.set_criticality("RES1", "CRIT_A")
    assert store.has_ack("RES1") is False
    store.record_ack(
        "RES1",
        {
            "channel": "phone",
            "receiver_role": "WARD_TEAM_PRIMARY",
            "receiver_name_or_id": "DR_X",
            "receiver_location_or_org": "WARD_Y",
            "read_back_confirmed": True,
            "outcome": "reached",
            "acknowledgment_ts_s": 100,
        },
        "A_SUPERVISOR",
        100,
    )
    assert store.has_ack("RES1") is True


def test_comm_record_exists() -> None:
    store = CriticalStore()
    assert store.comm_record_exists("RES_X") is False
    store.record_ack("RES_X", {"channel": "phone", "receiver_role": "R", "receiver_name_or_id": "X", "receiver_location_or_org": "Y", "read_back_confirmed": False, "outcome": "reached", "acknowledgment_ts_s": 3000}, "A_SUPERVISOR", 3000)
    assert store.comm_record_exists("RES_X") is True


# ---- CoreEnv GS-016, GS-017, GS-018 ----
def _should_run_golden() -> bool:
    return os.environ.get("LABTRUST_RUN_GOLDEN") == "1"


GS016 = {
    "scenario_id": "GS-016",
    "title": "Critical CRIT_A: release blocked until NOTIFY + ACK recorded",
    "initial_state": {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [],
    },
    "script": [
        {"event_id": "e1", "t_s": 2000, "agent_id": "A_ANALYTICS", "action_type": "GENERATE_RESULT", "args": {"result_id": "RES_CRITK", "analyte_code": "BIOCHEM_POTASSIUM_K", "value": 7.0, "units": "mmol/L", "qc_state": "pass"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["CLASSIFY_RESULT"], "state_assertions": ["result_criticality('RES_CRITK') == 'CRIT_A'"]}},
        {"event_id": "e2", "t_s": 2010, "agent_id": "A_ANALYTICS", "action_type": "RELEASE_RESULT", "args": {"result_id": "RES_CRITK"}, "reason_code": None, "token_refs": [], "expect": {"status": "BLOCKED", "blocked_reason_code": "CRIT_NO_ACK", "violations": ["INV-CRIT-002:VIOLATION"]}},
        {"event_id": "e3", "t_s": 2020, "agent_id": "A_SUPERVISOR", "action_type": "NOTIFY_CRITICAL_RESULT", "args": {"result_id": "RES_CRITK", "channel": "phone", "receiver_role": "WARD_TEAM_PRIMARY"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED"}},
        {"event_id": "e4", "t_s": 2030, "agent_id": "A_SUPERVISOR", "action_type": "ACK_CRITICAL_RESULT", "args": {"result_id": "RES_CRITK", "channel": "phone", "receiver_role": "WARD_TEAM_PRIMARY", "receiver_name_or_id": "WARD_CLINICIAN_1", "receiver_location_or_org": "WARD_X", "read_back_confirmed": True, "outcome": "reached", "acknowledgment_ts_s": 2030}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "violations": ["INV-CRIT-004:PASS"]}},
        {"event_id": "e5", "t_s": 2040, "agent_id": "A_ANALYTICS", "action_type": "RELEASE_RESULT", "args": {"result_id": "RES_CRITK"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED"}},
    ],
}

GS017 = {
    "scenario_id": "GS-017",
    "title": "Critical comm without read-back triggers audit violation (but ACK exists)",
    "initial_state": {"system": {}, "specimens": [], "tokens": []},
    "script": [
        {"event_id": "e1", "t_s": 3000, "agent_id": "A_SUPERVISOR", "action_type": "ACK_CRITICAL_RESULT", "args": {"result_id": "RES_X", "channel": "phone", "receiver_role": "WARD_TEAM_PRIMARY", "receiver_name_or_id": "WARD_CLINICIAN_2", "receiver_location_or_org": "WARD_Y", "read_back_confirmed": False, "outcome": "reached", "acknowledgment_ts_s": 3000}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "violations": ["INV-CRIT-004:VIOLATION"], "state_assertions": ["comm_record_exists(result_id='RES_X') == true"]}},
    ],
}

GS018 = {
    "scenario_id": "GS-018",
    "title": "Downtime forces oral notification path for critical result",
    "initial_state": {
        "system": {"now_s": 0, "downtime_active": True},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [],
    },
    "script": [
        {"event_id": "e1", "t_s": 4000, "agent_id": "A_ANALYTICS", "action_type": "GENERATE_RESULT", "args": {"result_id": "RES_DT", "analyte_code": "BIOCHEM_SODIUM_NA", "value": 165.0, "units": "mmol/L", "qc_state": "pass"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "emits": ["NOTIFY_CRITICAL_RESULT"], "state_assertions": ["notification_mode_required('RES_DT') == 'phone_or_bleep'"]}},
    ],
}


@pytest.mark.parametrize("scenario", [GS016, GS017, GS018], ids=["GS-016", "GS-017", "GS-018"])
def test_gs016_gs017_gs018(scenario: dict) -> None:
    """Run GS-016, GS-017, GS-018 with CoreEnv. Skipped unless LABTRUST_RUN_GOLDEN=1."""
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run critical scenarios.")
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
