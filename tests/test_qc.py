"""
QC model and result gating.

- engine/qc.py: device qc_state, results, RELEASE_RESULT gating.
- QC_EVENT fail => device qc_state fail; RELEASE_RESULT => BLOCKED QC_FAIL_ACTIVE, result held.
- QC_EVENT pass => allow release.
- RELEASE_RESULT_OVERRIDE with TOKEN_QC_DRIFT_OVERRIDE => result flag QC_DRIFT_DISCLAIMER_REQUIRED.
- query: result_status('...'), result_flags('...').
- GS-014, GS-015 pass when LABTRUST_RUN_GOLDEN=1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.engine.qc import QCStore
from labtrust_gym.runner import GoldenRunner


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---- engine/qc.py unit tests ----
def test_qc_store_device_state() -> None:
    qc = QCStore()
    assert qc.device_qc_state("DEV_X") == "pass"
    qc.set_device_qc_state("DEV_X", "fail")
    assert qc.device_qc_state("DEV_X") == "fail"
    qc.set_device_qc_state("DEV_X", "pass")
    assert qc.device_qc_state("DEV_X") == "pass"


def test_qc_store_run_result_release_blocked() -> None:
    qc = QCStore()
    qc.register_run("R1", "DEV_A")
    qc.set_device_qc_state("DEV_A", "fail")
    qc.create_result("RES1", "R1")
    assert qc.result_status("RES1") == "held"
    can_release, code = qc.can_release_result("RES1")
    assert can_release is False
    assert code == "QC_FAIL_ACTIVE"
    qc.hold_result("RES1")
    assert qc.result_status("RES1") == "held"


def test_qc_store_release_after_pass() -> None:
    qc = QCStore()
    qc.register_run("R1", "DEV_A")
    qc.set_device_qc_state("DEV_A", "fail")
    qc.create_result("RES1", "R1")
    qc.set_device_qc_state("DEV_A", "pass")
    can_release, code = qc.can_release_result("RES1")
    assert can_release is True
    assert code is None
    qc.release_result("RES1")
    assert qc.result_status("RES1") == "released"


def test_qc_store_release_override_drift_flag() -> None:
    qc = QCStore()
    qc.create_result("RES_DRIFT", "R1", qc_state="drift")
    qc.release_result_override_with_drift_flag("RES_DRIFT")
    assert qc.result_status("RES_DRIFT") == "released"
    assert "QC_DRIFT_DISCLAIMER_REQUIRED" in qc.result_flags("RES_DRIFT")


# ---- CoreEnv GS-014, GS-015 ----
def _should_run_golden() -> bool:
    return os.environ.get("LABTRUST_RUN_GOLDEN") == "1"


GS014 = {
    "scenario_id": "GS-014",
    "title": "QC fail cascade blocks release (non-overridable) until rerun clears",
    "initial_state": {
        "system": {},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 1000,
            "agent_id": "A_ANALYTICS",
            "action_type": "START_RUN",
            "args": {"device_id": "DEV_CHEM_A_01", "run_id": "R_QCFAIL", "specimen_ids": ["S1"]},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED"},
        },
        {
            "event_id": "e2",
            "t_s": 1100,
            "agent_id": "A_QC",
            "action_type": "QC_EVENT",
            "args": {"device_id": "DEV_CHEM_A_01", "run_id": "R_QCFAIL", "qc_outcome": "fail"},
            "reason_code": "QC_FAIL_ACTIVE",
            "token_refs": [],
            "expect": {"status": "ACCEPTED", "emits": ["QC_EVENT"]},
        },
        {
            "event_id": "e3",
            "t_s": 1110,
            "agent_id": "A_ANALYTICS",
            "action_type": "GENERATE_RESULT",
            "args": {
                "run_id": "R_QCFAIL",
                "result_id": "RES_QC1",
                "analyte_code": "BIOCHEM_SODIUM_NA",
                "value": 140.0,
                "units": "mmol/L",
            },
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED"},
        },
        {
            "event_id": "e4",
            "t_s": 1120,
            "agent_id": "A_ANALYTICS",
            "action_type": "RELEASE_RESULT",
            "args": {"result_id": "RES_QC1"},
            "reason_code": None,
            "token_refs": [],
            "expect": {
                "status": "BLOCKED",
                "blocked_reason_code": "QC_FAIL_ACTIVE",
                "state_assertions": ["result_status('RES_QC1') == 'held'"],
            },
        },
        {
            "event_id": "e5",
            "t_s": 1200,
            "agent_id": "A_ANALYTICS",
            "action_type": "RERUN_REQUEST",
            "args": {"result_id": "RES_QC1", "reason_code": "QC_FAIL_ACTIVE"},
            "reason_code": "QC_FAIL_ACTIVE",
            "token_refs": [],
            "expect": {"status": "ACCEPTED"},
        },
        {
            "event_id": "e6",
            "t_s": 1300,
            "agent_id": "A_QC",
            "action_type": "QC_EVENT",
            "args": {"device_id": "DEV_CHEM_A_01", "run_id": "R_QCPASS2", "qc_outcome": "pass"},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED"},
        },
        {
            "event_id": "e7",
            "t_s": 1310,
            "agent_id": "A_ANALYTICS",
            "action_type": "RELEASE_RESULT",
            "args": {"result_id": "RES_QC1"},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED"},
        },
    ],
}

GS015 = {
    "scenario_id": "GS-015",
    "title": "QC drift suspected: release requires TOKEN_QC_DRIFT_OVERRIDE",
    "initial_state": {
        "system": {},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [
            {
                "token_id": "T_QC_DRIFT",
                "token_type": "TOKEN_QC_DRIFT_OVERRIDE",
                "state": "ACTIVE",
                "subject_type": "result",
                "subject_id": "RES_DRIFT",
                "issued_at_ts_s": 0,
                "expires_at_ts_s": 1800,
                "reason_code": "QC_DRIFT_SUSPECTED",
            }
        ],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 1000,
            "agent_id": "A_ANALYTICS",
            "action_type": "GENERATE_RESULT",
            "args": {
                "result_id": "RES_DRIFT",
                "analyte_code": "BIOCHEM_POTASSIUM_K",
                "value": 4.5,
                "units": "mmol/L",
                "qc_state": "drift",
            },
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED"},
        },
        {
            "event_id": "e2",
            "t_s": 1010,
            "agent_id": "A_ANALYTICS",
            "action_type": "RELEASE_RESULT_OVERRIDE",
            "args": {"result_id": "RES_DRIFT", "reason_code": "QC_DRIFT_SUSPECTED"},
            "reason_code": "QC_DRIFT_SUSPECTED",
            "token_refs": ["T_QC_DRIFT"],
            "expect": {
                "status": "ACCEPTED",
                "token_consumed": ["T_QC_DRIFT"],
                "state_assertions": ["result_flags('RES_DRIFT') contains 'QC_DRIFT_DISCLAIMER_REQUIRED'"],
            },
        },
    ],
}


@pytest.mark.parametrize("scenario", [GS014, GS015], ids=["GS-014", "GS-015"])
def test_gs014_gs015(scenario: dict) -> None:
    """Run GS-014, GS-015 with CoreEnv. Skipped unless LABTRUST_RUN_GOLDEN=1."""
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run QC scenarios.")
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
