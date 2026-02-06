"""
Reception acceptance rules and specimen state machine.

- engine/specimens.py: SpecimenStore, CREATE_ACCESSION, CHECK_ACCEPTANCE_RULES,
  ACCEPT_SPECIMEN (ID_MISMATCH, INT_LEAKING, CNT_CITRATE_FILL_INVALID), HOLD_SPECIMEN (reason_code).
- BLOCKED actions do not mutate specimen state.
- GS-003: citrate underfill => HOLD_SPECIMEN, CNT_CITRATE_FILL_INVALID, INV-COAG-FILL-001.
- GS-004: id_match false => REJECT_SPECIMEN, ID_MISMATCH.
- GS-005: leak => REJECT_SPECIMEN, INT_LEAKING.
- GS-021: HOLD_SPECIMEN without reason_code => BLOCKED AUDIT_MISSING_REASON_CODE.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.engine.specimens import (
    CNT_CITRATE_FILL_INVALID,
    ID_MISMATCH,
    INT_LEAKING,
    INV_COAG_FILL_001,
    SpecimenStore,
    _expand_specimen,
)
from labtrust_gym.runner import GoldenRunner


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---- engine/specimens.py unit tests ----
def test_expand_specimen_template() -> None:
    entry = {"template_ref": "S_BIOCHEM_OK"}
    spec = _expand_specimen(entry)
    assert spec["specimen_id"] == "S1"
    assert spec["status"] == "arrived_at_reception"
    assert spec.get("panel_id") == "BIOCHEM_PANEL_CORE"


def test_specimen_store_accept_id_mismatch() -> None:
    store = SpecimenStore()
    store.load_initial([{"template_ref": "S_BIOCHEM_OK"}])
    store.check_acceptance_rules("S1", id_match=False)
    outcome, emits, blocked, violations = store.accept_specimen("S1")
    assert outcome == "ACCEPTED"
    assert "REJECT_SPECIMEN" in emits
    assert store.specimen_status("S1") == "rejected"
    assert store.last_reason_code("S1") == ID_MISMATCH


def test_specimen_store_accept_leak() -> None:
    store = SpecimenStore()
    store.load_initial(
        [
            {
                "specimen_id": "S3",
                "integrity_flags": {"leak": True},
                "hazard_flag": True,
                "status": "arrived_at_reception",
            }
        ]
    )
    outcome, emits, blocked, violations = store.accept_specimen("S3")
    assert outcome == "ACCEPTED"
    assert "REJECT_SPECIMEN" in emits
    assert store.specimen_status("S3") == "rejected"
    assert store.last_reason_code("S3") == INT_LEAKING


def test_specimen_store_accept_citrate_underfill() -> None:
    store = SpecimenStore()
    store.load_initial(
        [
            {
                "specimen_id": "S2",
                "container_type": "PLASMA_CITRATE",
                "fill_ratio_ok": False,
                "status": "arrived_at_reception",
            }
        ]
    )
    outcome, emits, blocked, violations = store.accept_specimen("S2")
    assert outcome == "ACCEPTED"
    assert "HOLD_SPECIMEN" in emits
    assert store.specimen_status("S2") == "held"
    assert store.last_reason_code("S2") == CNT_CITRATE_FILL_INVALID
    assert any(v["invariant_id"] == INV_COAG_FILL_001 for v in violations)


def test_hold_specimen_without_reason_code_blocked() -> None:
    store = SpecimenStore()
    store.load_initial([{"template_ref": "S_BIOCHEM_OK"}])
    ok, blocked_code = store.hold_specimen("S1", None)
    assert ok is False
    assert blocked_code == "AUDIT_MISSING_REASON_CODE"
    assert store.specimen_status("S1") == "arrived_at_reception"


def test_hold_specimen_with_reason_code_mutates() -> None:
    store = SpecimenStore()
    store.load_initial([{"template_ref": "S_BIOCHEM_OK"}])
    ok, blocked_code = store.hold_specimen("S1", "INT_INSUFFICIENT_VOLUME")
    assert ok is True
    assert blocked_code is None
    assert store.specimen_status("S1") == "held"
    assert store.last_reason_code("S1") == "INT_INSUFFICIENT_VOLUME"


# ---- CoreEnv GS-003, GS-004, GS-005, GS-021 ----
def _should_run_golden() -> bool:
    return os.environ.get("LABTRUST_RUN_GOLDEN") == "1"


GS003 = {
    "scenario_id": "GS-003",
    "title": "Coagulation citrate underfill is hard-stop (non-overridable)",
    "initial_state": {
        "system": {},
        "specimens": [
            {
                "specimen_id": "S2",
                "patient_identifiers_hash": "pid:hash:002",
                "collection_ts_s": 0,
                "arrival_ts_s": 600,
                "panel_id": "COAG_PANEL_CORE",
                "container_type": "PLASMA_CITRATE",
                "specimen_type": "PLASMA",
                "integrity_flags": {
                    "leak": False,
                    "clot": False,
                    "hemolysis": False,
                    "insufficient_volume": False,
                    "label_issue": False,
                },
                "fill_ratio_ok": False,
                "hazard_flag": False,
                "separated_ts_s": None,
                "temp_band": "AMBIENT_20_25",
                "status": "arrived_at_reception",
            }
        ],
        "tokens": [],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 610,
            "agent_id": "A_RECEPTION",
            "action_type": "CHECK_ACCEPTANCE_RULES",
            "args": {"specimen_id": "S2"},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED", "emits": ["CHECK_ACCEPTANCE_RULES"]},
        },
        {
            "event_id": "e2",
            "t_s": 620,
            "agent_id": "A_RECEPTION",
            "action_type": "ACCEPT_SPECIMEN",
            "args": {"specimen_id": "S2"},
            "reason_code": None,
            "token_refs": [],
            "expect": {
                "status": "ACCEPTED",
                "emits": ["HOLD_SPECIMEN"],
                "violations": ["INV-COAG-FILL-001:VIOLATION"],
            },
        },
    ],
}

GS004 = {
    "scenario_id": "GS-004",
    "title": "Identity mismatch is non-overridable hard-stop",
    "initial_state": {"system": {}, "specimens": [{"template_ref": "S_BIOCHEM_OK"}], "tokens": []},
    "script": [
        {
            "event_id": "e1",
            "t_s": 610,
            "agent_id": "A_RECEPTION",
            "action_type": "CHECK_ACCEPTANCE_RULES",
            "args": {"specimen_id": "S1", "id_match": False},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED"},
        },
        {
            "event_id": "e2",
            "t_s": 620,
            "agent_id": "A_RECEPTION",
            "action_type": "ACCEPT_SPECIMEN",
            "args": {"specimen_id": "S1"},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED", "emits": ["REJECT_SPECIMEN"]},
        },
    ],
}

GS005 = {
    "scenario_id": "GS-005",
    "title": "Leaking specimen is non-overridable reject + biohazard protocol",
    "initial_state": {
        "system": {},
        "specimens": [
            {
                "specimen_id": "S3",
                "patient_identifiers_hash": "pid:hash:003",
                "collection_ts_s": 0,
                "arrival_ts_s": 600,
                "panel_id": "BIOCHEM_PANEL_CORE",
                "container_type": "SERUM_SST",
                "specimen_type": "SERUM",
                "integrity_flags": {
                    "leak": True,
                    "clot": False,
                    "hemolysis": False,
                    "insufficient_volume": False,
                    "label_issue": False,
                },
                "fill_ratio_ok": None,
                "hazard_flag": True,
                "separated_ts_s": None,
                "temp_band": "AMBIENT_20_25",
                "status": "arrived_at_reception",
            }
        ],
        "tokens": [],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 620,
            "agent_id": "A_RECEPTION",
            "action_type": "ACCEPT_SPECIMEN",
            "args": {"specimen_id": "S3"},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED", "emits": ["REJECT_SPECIMEN"]},
        }
    ],
}

GS021 = {
    "scenario_id": "GS-021",
    "title": "Audit: HOLD_SPECIMEN without reason_code is blocked",
    "initial_state": {"system": {}, "specimens": [{"template_ref": "S_BIOCHEM_OK"}], "tokens": []},
    "script": [
        {
            "event_id": "e1",
            "t_s": 7000,
            "agent_id": "A_RECEPTION",
            "action_type": "HOLD_SPECIMEN",
            "args": {"specimen_id": "S1"},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "BLOCKED", "blocked_reason_code": "AUDIT_MISSING_REASON_CODE"},
        }
    ],
}


@pytest.mark.parametrize("scenario", [GS003, GS004, GS005, GS021], ids=["GS-003", "GS-004", "GS-005", "GS-021"])
def test_gs003_gs004_gs005_gs021(scenario: dict) -> None:
    """Run GS-003, GS-004, GS-005, GS-021 with CoreEnv. Skipped unless LABTRUST_RUN_GOLDEN=1."""
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run reception scenarios.")
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


def test_query_specimen_status_and_last_reason_code() -> None:
    """Query specimen_status and last_reason_code after ACCEPT_SPECIMEN (citrate underfill)."""
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1")
    env = CoreEnv()
    env.reset(GS003["initial_state"], deterministic=True, rng_seed=12345)
    env.step(
        {
            "event_id": "e1",
            "t_s": 610,
            "agent_id": "A_RECEPTION",
            "action_type": "CHECK_ACCEPTANCE_RULES",
            "args": {"specimen_id": "S2"},
            "reason_code": None,
            "token_refs": [],
        }
    )
    env.step(
        {
            "event_id": "e2",
            "t_s": 620,
            "agent_id": "A_RECEPTION",
            "action_type": "ACCEPT_SPECIMEN",
            "args": {"specimen_id": "S2"},
            "reason_code": None,
            "token_refs": [],
        }
    )
    assert env.query("specimen_status('S2')") == "held"
    assert env.query("last_reason_code('S2')") == CNT_CITRATE_FILL_INVALID
