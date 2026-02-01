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
    CRIT_ACK_MISSING_FIELDS,
    CRIT_ESCALATION_OUT_OF_ORDER,
    CriticalStore,
    classify_criticality,
    default_thresholds,
    load_escalation_ladder,
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


# ---- Critical v0.2: escalation ladder, ACK contract, escalation order, timeout ----
def test_escalation_ladder_schema_loads_and_has_tiers() -> None:
    """Escalation ladder YAML loads and has version, minimum_record_fields, tiers (schema enforced via validate_policy)."""
    root = _repo_root()
    path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
    if not path.exists():
        pytest.skip("policy/critical/escalation_ladder.v0.2.yaml not found")
    ladder = load_escalation_ladder(path)
    assert ladder is not None
    assert "version" in ladder
    assert "minimum_record_fields" in ladder
    assert "tiers" in ladder
    assert len(ladder["tiers"]) >= 1
    tier0 = ladder["tiers"][0]
    assert "tier_index" in tier0 and "role" in tier0
    assert "allowed_contact_modes" in tier0 and "max_ack_wait_s" in tier0


def test_critical_v02_ack_missing_attempt_id_rejected() -> None:
    """With ladder: ACK without attempt_id => BLOCKED CRIT_ACK_MISSING_FIELDS."""
    root = _repo_root()
    ladder_path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
    if not ladder_path.exists():
        pytest.skip("escalation_ladder.v0.2.yaml not found")
    ladder = load_escalation_ladder(ladder_path)
    store = CriticalStore(thresholds=default_thresholds(), ladder=ladder)
    store.set_criticality("RES_MISS", "CRIT_A")
    attempt_id, reason = store.record_notify("RES_MISS", "phone", "primary_contact", "A_SUPERVISOR", 2010)
    assert attempt_id == "RES_MISS_attempt_0"
    assert reason is None
    args_no_attempt_id = {
        "result_id": "RES_MISS",
        "channel": "phone",
        "receiver_role": "primary_contact",
        "receiver_name_or_id": "DR_X",
        "receiver_location_or_org": "WARD_Z",
        "read_back_confirmed": True,
        "outcome": "reached",
        "acknowledgment_ts_s": 2020,
    }
    ok, violation_id, reason_code = store.record_ack("RES_MISS", args_no_attempt_id, "A_SUPERVISOR", 2020)
    assert ok is False
    assert reason_code == CRIT_ACK_MISSING_FIELDS


def test_critical_v02_ack_wrong_attempt_id_rejected() -> None:
    """With ladder: ACK with non-existent attempt_id => BLOCKED CRIT_ACK_MISSING_FIELDS."""
    root = _repo_root()
    ladder_path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
    if not ladder_path.exists():
        pytest.skip("escalation_ladder.v0.2.yaml not found")
    ladder = load_escalation_ladder(ladder_path)
    store = CriticalStore(thresholds=default_thresholds(), ladder=ladder)
    store.set_criticality("RES_X", "CRIT_A")
    store.record_notify("RES_X", "phone", "primary_contact", "A_SUPERVISOR", 2010)
    args_bad_attempt_id = {
        "result_id": "RES_X",
        "attempt_id": "RES_X_attempt_99",
        "channel": "phone",
        "receiver_role": "primary_contact",
        "receiver_name_or_id": "DR_X",
        "receiver_location_or_org": "WARD_Z",
        "read_back_confirmed": True,
        "outcome": "reached",
        "acknowledgment_ts_s": 2020,
    }
    ok, _, reason_code = store.record_ack("RES_X", args_bad_attempt_id, "A_SUPERVISOR", 2020)
    assert ok is False
    assert reason_code == CRIT_ACK_MISSING_FIELDS


def test_critical_v02_escalate_out_of_order_blocked() -> None:
    """ESCALATE to tier 3 (duty_manager) when current tier is 0 => CRIT_ESCALATION_OUT_OF_ORDER."""
    root = _repo_root()
    ladder_path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
    if not ladder_path.exists():
        pytest.skip("escalation_ladder.v0.2.yaml not found")
    ladder = load_escalation_ladder(ladder_path)
    store = CriticalStore(thresholds=default_thresholds(), ladder=ladder)
    store.set_criticality("RES_ESC", "CRIT_A")
    store.record_notify("RES_ESC", "phone", "primary_contact", "A_SUPERVISOR", 2010)
    ok, reason_code = store.record_escalate("RES_ESC", "duty_manager", "A_SUPERVISOR", 2020)
    assert ok is False
    assert reason_code == CRIT_ESCALATION_OUT_OF_ORDER


def test_critical_v02_escalate_in_order_accepted() -> None:
    """ESCALATE to tier 1 (secondary) after tier 0 => accepted."""
    root = _repo_root()
    ladder_path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
    if not ladder_path.exists():
        pytest.skip("escalation_ladder.v0.2.yaml not found")
    ladder = load_escalation_ladder(ladder_path)
    store = CriticalStore(thresholds=default_thresholds(), ladder=ladder)
    store.set_criticality("RES_ESC", "CRIT_A")
    store.record_notify("RES_ESC", "phone", "primary_contact", "A_SUPERVISOR", 2010)
    ok, reason_code = store.record_escalate("RES_ESC", "secondary", "A_SUPERVISOR", 2020)
    assert ok is True
    assert reason_code is None
    assert len(store._attempts["RES_ESC"]) == 2
    assert store._attempts["RES_ESC"][1].get("callee_role") == "secondary"
    assert store._attempts["RES_ESC"][1].get("attempt_id") == "RES_ESC_attempt_1"


def test_critical_v02_can_escalate_after_timeout() -> None:
    """can_escalate False before max_ack_wait_s, True after (tier 0 max_ack_wait_s=300)."""
    root = _repo_root()
    ladder_path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
    if not ladder_path.exists():
        pytest.skip("escalation_ladder.v0.2.yaml not found")
    ladder = load_escalation_ladder(ladder_path)
    store = CriticalStore(thresholds=default_thresholds(), ladder=ladder)
    store.set_criticality("RES_TMO", "CRIT_A")
    store.record_notify("RES_TMO", "phone", "primary_contact", "A_SUPERVISOR", 2010)
    assert store.can_escalate("RES_TMO", 2010 + 100) is False
    assert store.can_escalate("RES_TMO", 2010 + 299) is False
    assert store.can_escalate("RES_TMO", 2010 + 300) is True
    assert store.can_escalate("RES_TMO", 2010 + 400) is True


def test_critical_v02_timeout_escalate_then_ack_release() -> None:
    """Timeout -> ESCALATE to secondary -> ACK attempt_1 -> has_ack True (release allowed)."""
    root = _repo_root()
    ladder_path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
    if not ladder_path.exists():
        pytest.skip("escalation_ladder.v0.2.yaml not found")
    ladder = load_escalation_ladder(ladder_path)
    store = CriticalStore(thresholds=default_thresholds(), ladder=ladder)
    store.set_criticality("RES_TMO", "CRIT_A")
    store.record_notify("RES_TMO", "phone", "primary_contact", "A_SUPERVISOR", 2010)
    assert store.has_ack("RES_TMO") is False
    ok, _ = store.record_escalate("RES_TMO", "secondary", "A_SUPERVISOR", 2510)
    assert ok is True
    ok, violation_id, reason_code = store.record_ack(
        "RES_TMO",
        {
            "result_id": "RES_TMO",
            "attempt_id": "RES_TMO_attempt_1",
            "channel": "phone",
            "receiver_role": "secondary",
            "receiver_name_or_id": "DR_Y",
            "receiver_location_or_org": "WARD_W",
            "read_back_confirmed": True,
            "outcome": "reached",
            "acknowledgment_ts_s": 2520,
        },
        "A_SUPERVISOR",
        2520,
    )
    assert ok is True
    assert store.has_ack("RES_TMO") is True


def test_critical_v02_determinism_attempt_ids() -> None:
    """Same notify -> escalate -> ack sequence yields same attempt_ids (determinism)."""
    root = _repo_root()
    ladder_path = root / "policy" / "critical" / "escalation_ladder.v0.2.yaml"
    if not ladder_path.exists():
        pytest.skip("escalation_ladder.v0.2.yaml not found")
    ladder = load_escalation_ladder(ladder_path)
    store = CriticalStore(thresholds=default_thresholds(), ladder=ladder)
    store.set_criticality("R", "CRIT_A")
    a1, _ = store.record_notify("R", "phone", "primary_contact", "A1", 100)
    ok, _ = store.record_escalate("R", "secondary", "A1", 500)
    assert ok is True
    attempt_ids = [a["attempt_id"] for a in store._attempts["R"]]
    assert attempt_ids == ["R_attempt_0", "R_attempt_1"]
    assert a1 == "R_attempt_0"


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
        {"event_id": "e4", "t_s": 2030, "agent_id": "A_SUPERVISOR", "action_type": "ACK_CRITICAL_RESULT", "args": {"result_id": "RES_CRITK", "attempt_id": "RES_CRITK_attempt_0", "channel": "phone", "receiver_role": "WARD_TEAM_PRIMARY", "receiver_name_or_id": "WARD_CLINICIAN_1", "receiver_location_or_org": "WARD_X", "read_back_confirmed": True, "outcome": "reached", "acknowledgment_ts_s": 2030}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "violations": ["INV-CRIT-004:PASS"]}},
        {"event_id": "e5", "t_s": 2040, "agent_id": "A_ANALYTICS", "action_type": "RELEASE_RESULT", "args": {"result_id": "RES_CRITK"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED"}},
    ],
}

GS017 = {
    "scenario_id": "GS-017",
    "title": "Critical comm without read-back triggers audit violation (but ACK exists)",
    "initial_state": {"system": {}, "specimens": [], "tokens": []},
    "script": [
        {"event_id": "e0", "t_s": 2990, "agent_id": "A_SUPERVISOR", "action_type": "NOTIFY_CRITICAL_RESULT", "args": {"result_id": "RES_X", "channel": "phone", "receiver_role": "primary_contact"}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED"}},
        {"event_id": "e1", "t_s": 3000, "agent_id": "A_SUPERVISOR", "action_type": "ACK_CRITICAL_RESULT", "args": {"result_id": "RES_X", "attempt_id": "RES_X_attempt_0", "channel": "phone", "receiver_role": "WARD_TEAM_PRIMARY", "receiver_name_or_id": "WARD_CLINICIAN_2", "receiver_location_or_org": "WARD_Y", "read_back_confirmed": False, "outcome": "reached", "acknowledgment_ts_s": 3000}, "reason_code": None, "token_refs": [], "expect": {"status": "ACCEPTED", "violations": ["INV-CRIT-004:VIOLATION"], "state_assertions": ["comm_record_exists(result_id='RES_X') == true"]}},
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
