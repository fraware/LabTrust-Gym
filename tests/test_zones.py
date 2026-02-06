"""
Zone graph and door semantics.

- engine/zones.py: adjacency, doors, agent positions, open_since_ts, tick, zone_state.
- MOVE: not adjacent => BLOCKED RC_ILLEGAL_MOVE, INV-ZONE-001.
- OPEN_DOOR restricted without token => BLOCKED RBAC_RESTRICTED_ENTRY_DENY (core_env).
- Door open too long => INV-ZONE-005, ALARM, KILL_SWITCH_ZONE, zone frozen.
- query: zone_state('Z_RESTRICTED_BIOHAZARD') == 'frozen' | 'normal'.
- GS-008, GS-009, GS-020 pass when LABTRUST_RUN_GOLDEN=1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.engine.zones import (
    ZoneState,
    build_adjacency_set,
    build_device_zone_map,
    build_doors_map,
    load_zone_layout,
)
from labtrust_gym.runner import GoldenRunner


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# ---- zones.py unit tests ----
def test_build_adjacency_set() -> None:
    edges = [
        {"from": "Z_A", "to": "Z_B"},
        {"from": "Z_B", "to": "Z_C"},
    ]
    adj = build_adjacency_set(edges)
    assert ("Z_A", "Z_B") in adj
    assert ("Z_B", "Z_A") in adj
    assert ("Z_B", "Z_C") in adj
    assert ("Z_SRA_RECEPTION", "Z_RESTRICTED_BIOHAZARD") not in adj


def test_build_device_zone_map() -> None:
    """device_placement list -> device_id -> zone_id."""
    placement = [
        {"device_id": "DEV_CHEM_A_01", "zone_id": "Z_ANALYZER_HALL_A"},
        {"device_id": "DEV_CENTRIFUGE_BANK_01", "zone_id": "Z_CENTRIFUGE_BAY"},
    ]
    m = build_device_zone_map(placement)
    assert m["DEV_CHEM_A_01"] == "Z_ANALYZER_HALL_A"
    assert m["DEV_CENTRIFUGE_BANK_01"] == "Z_CENTRIFUGE_BAY"
    assert build_device_zone_map([]) == {}
    assert build_device_zone_map([{"device_id": "X"}]) == {}


def test_build_doors_map() -> None:
    doors = [
        {
            "door_id": "D_RESTRICTED_AIRLOCK",
            "from_zone": "Z_SRA",
            "to_zone": "Z_RESTRICTED",
            "max_open_s": 120,
            "requires_token": "TOKEN_RESTRICTED_ENTRY",
        },
    ]
    m = build_doors_map(doors)
    assert "D_RESTRICTED_AIRLOCK" in m
    assert m["D_RESTRICTED_AIRLOCK"]["max_open_s"] == 120
    assert m["D_RESTRICTED_AIRLOCK"]["restricted"] is True


def test_zone_state_move_adjacent() -> None:
    z = ZoneState(None)
    z.reset(None)
    ok, violations, code = z.move("A_RUNNER", "Z_SORTING_LANES", "Z_PREANALYTICS")
    assert ok is True
    assert violations == []
    assert code is None
    assert z.get_agent_zone("A_RUNNER") == "Z_PREANALYTICS"


def test_zone_state_move_not_adjacent() -> None:
    z = ZoneState(None)
    z.reset(None)
    ok, violations, code = z.move("A_RUNNER", "Z_SORTING_LANES", "Z_RESTRICTED_BIOHAZARD")
    assert ok is False
    assert any(v["invariant_id"] == "INV-ZONE-001" for v in violations)
    assert any(v["invariant_id"] == "INV-ZONE-004" for v in violations)
    assert code == "RC_ILLEGAL_MOVE"


def test_zone_state_open_door_tick_freeze() -> None:
    z = ZoneState(None)
    z.reset(None)
    z.open_door("D_RESTRICTED_AIRLOCK", 700)
    violations, emits = z.tick(900)
    assert violations == [] and emits == []
    violations, emits = z.tick(1030)
    assert any(v["invariant_id"] == "INV-ZONE-005" for v in violations)
    assert "ALARM" in emits
    assert "KILL_SWITCH_ZONE" in emits
    assert z.zone_state("Z_RESTRICTED_BIOHAZARD") == "frozen"


def test_zone_state_query_normal() -> None:
    z = ZoneState(None)
    assert z.zone_state("Z_QC_SUPERVISOR") == "normal"


def test_load_zone_layout_if_exists() -> None:
    root = _repo_root()
    path = root / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
    if not path.exists():
        pytest.skip("Zone layout policy not found")
    layout = load_zone_layout(path)
    assert "graph_edges" in layout
    assert "doors" in layout
    adj = build_adjacency_set(layout["graph_edges"])
    assert ("Z_SRA_RECEPTION", "Z_RESTRICTED_BIOHAZARD") in adj


# ---- CoreEnv GS-008, GS-009, GS-020 ----
def _should_run_golden() -> bool:
    return os.environ.get("LABTRUST_RUN_GOLDEN") == "1"


GS008 = {
    "scenario_id": "GS-008",
    "title": "Restricted airlock cannot open without TOKEN_RESTRICTED_ENTRY",
    "initial_state": {"system": {}, "specimens": [], "tokens": []},
    "script": [
        {
            "event_id": "e1",
            "t_s": 700,
            "agent_id": "A_RUNNER",
            "action_type": "OPEN_DOOR",
            "args": {"door_id": "D_RESTRICTED_AIRLOCK"},
            "reason_code": None,
            "token_refs": [],
            "expect": {
                "status": "BLOCKED",
                "blocked_reason_code": "RBAC_RESTRICTED_ENTRY_DENY",
                "violations": ["INV-ZONE-004:VIOLATION", "INV-TOK-003:VIOLATION"],
            },
        }
    ],
}

GS009 = {
    "scenario_id": "GS-009",
    "title": "Restricted door open too long triggers alarm + zone kill-switch",
    "initial_state": {
        "system": {},
        "specimens": [],
        "tokens": [
            {
                "token_id": "T_RESTRICT_1",
                "token_type": "TOKEN_RESTRICTED_ENTRY",
                "state": "ACTIVE",
                "subject_type": "agent",
                "subject_id": "A_SUPERVISOR",
                "issued_at_ts_s": 690,
                "expires_at_ts_s": 1590,
                "reason_code": "SYS_DOWNTIME_ACTIVE",
            }
        ],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 700,
            "agent_id": "A_SUPERVISOR",
            "action_type": "OPEN_DOOR",
            "args": {"door_id": "D_RESTRICTED_AIRLOCK"},
            "reason_code": "SYS_DOWNTIME_ACTIVE",
            "token_refs": ["T_RESTRICT_1"],
            "expect": {"status": "ACCEPTED"},
        },
        {
            "event_id": "e2",
            "t_s": 900,
            "agent_id": "A_SUPERVISOR",
            "action_type": "TICK",
            "args": {},
            "reason_code": None,
            "token_refs": [],
            "expect": {"status": "ACCEPTED", "violations": []},
        },
        {
            "event_id": "e3",
            "t_s": 1030,
            "agent_id": "A_SUPERVISOR",
            "action_type": "TICK",
            "args": {},
            "reason_code": None,
            "token_refs": [],
            "expect": {
                "status": "ACCEPTED",
                "violations": ["INV-ZONE-005:VIOLATION"],
                "emits": ["ALARM", "KILL_SWITCH_ZONE"],
                "state_assertions": ["zone_state('Z_RESTRICTED_BIOHAZARD') == 'frozen'"],
            },
        },
    ],
}

GS019 = {
    "scenario_id": "GS-019",
    "title": "Device action blocked if agent not co-located in device zone",
    "initial_state": {
        "system": {"now_s": 0, "downtime_active": False},
        "specimens": [{"template_ref": "S_BIOCHEM_OK"}],
        "tokens": [],
    },
    "script": [
        {
            "event_id": "e1",
            "t_s": 5000,
            "agent_id": "A_RECEPTION",
            "action_type": "START_RUN",
            "args": {
                "device_id": "DEV_CHEM_A_01",
                "run_id": "R_BADLOC",
                "specimen_ids": ["S1"],
            },
            "reason_code": None,
            "token_refs": [],
            "expect": {
                "status": "BLOCKED",
                "blocked_reason_code": "RC_DEVICE_NOT_COLOCATED",
                "violations": ["INV-ZONE-002:VIOLATION"],
            },
        }
    ],
}

GS020 = {
    "scenario_id": "GS-020",
    "title": "Illegal move not on graph is blocked",
    "initial_state": {"system": {}, "specimens": [], "tokens": []},
    "script": [
        {
            "event_id": "e1",
            "t_s": 6000,
            "agent_id": "A_RUNNER",
            "action_type": "MOVE",
            "args": {
                "entity_type": "Agent",
                "entity_id": "A_RUNNER",
                "from_zone": "Z_SORTING_LANES",
                "to_zone": "Z_RESTRICTED_BIOHAZARD",
            },
            "reason_code": None,
            "token_refs": [],
            "expect": {
                "status": "BLOCKED",
                "violations": ["INV-ZONE-001:VIOLATION", "INV-ZONE-004:VIOLATION"],
            },
        }
    ],
}


@pytest.mark.parametrize("scenario", [GS008, GS009, GS019, GS020], ids=["GS-008", "GS-009", "GS-019", "GS-020"])
def test_gs008_gs009_gs019_gs020(scenario: dict) -> None:
    """Run GS-008, GS-009, GS-019, GS-020 with CoreEnv. Skipped unless LABTRUST_RUN_GOLDEN=1."""
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run zone scenarios.")
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


def test_colocation_unit_agent_not_in_device_zone() -> None:
    """START_RUN from agent in Z_SRA_RECEPTION for device in Z_ANALYZER_HALL_A -> BLOCKED."""
    if not _should_run_golden():
        pytest.skip("Set LABTRUST_RUN_GOLDEN=1 to run colocation test.")
    root = _repo_root()
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if not emits_path.exists():
        emits_path = root / "emits_vocab.v0.1.yaml"
    env = CoreEnv()
    env.reset(
        {"system": {}, "specimens": [{"template_ref": "S_BIOCHEM_OK"}], "tokens": []},
        deterministic=True,
        rng_seed=12345,
    )
    event = {
        "event_id": "e1",
        "t_s": 5000,
        "agent_id": "A_RECEPTION",
        "action_type": "START_RUN",
        "args": {
            "device_id": "DEV_CHEM_A_01",
            "run_id": "R_BADLOC",
            "specimen_ids": ["S1"],
        },
        "reason_code": None,
        "token_refs": [],
    }
    out = env.step(event)
    assert out["status"] == "BLOCKED"
    assert out.get("blocked_reason_code") == "RC_DEVICE_NOT_COLOCATED"
    violations = out.get("violations", [])
    assert any(v.get("invariant_id") == "INV-ZONE-002" and v.get("status") == "VIOLATION" for v in violations)
