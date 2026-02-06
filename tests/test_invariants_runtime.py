"""
Invariants runtime: compile registry into checks, evaluate post-step, return violations.
"""

from pathlib import Path

import pytest

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.engine.invariants_runtime import (
    InvariantsRuntime,
    merge_violations_by_invariant_id,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_invariants_runtime_loads_registry() -> None:
    """InvariantsRuntime loads registry and has entries."""
    root = _repo_root()
    reg_path = root / "policy/invariants/invariant_registry.v1.0.yaml"
    if not reg_path.exists():
        pytest.skip("invariant_registry.v1.0.yaml not found")
    runtime = InvariantsRuntime(reg_path)
    assert runtime._entries
    assert len(runtime._by_id) >= 1


def test_invariants_runtime_evaluate_returns_list() -> None:
    """evaluate(env, event, result) returns list of violation items."""
    root = _repo_root()
    reg_path = root / "policy/invariants/invariant_registry.v1.0.yaml"
    if not reg_path.exists():
        pytest.skip("invariant_registry.v1.0.yaml not found")
    runtime = InvariantsRuntime(reg_path)
    env = CoreEnv()
    initial = {
        "system": {"now_s": 0, "downtime_active": False},
        "agents": [{"agent_id": "A1", "zone_id": "Z_SRA_RECEPTION"}],
        "specimens": [],
        "tokens": [],
    }
    env.reset(initial, deterministic=True, rng_seed=42)
    event = {
        "event_id": "e1",
        "t_s": 100,
        "agent_id": "A1",
        "action_type": "TICK",
        "args": {},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    violations = runtime.evaluate(env, event, result)
    assert isinstance(violations, list)
    for v in violations:
        assert "invariant_id" in v
        assert "status" in v
        assert v["status"] in ("PASS", "VIOLATION")


def test_merge_violations_by_invariant_id() -> None:
    """Registry violations overwrite legacy for same invariant_id."""
    legacy = [
        {"invariant_id": "INV-ZONE-002", "status": "PASS"},
        {"invariant_id": "INV-X", "status": "VIOLATION"},
    ]
    registry = [
        {"invariant_id": "INV-ZONE-002", "status": "VIOLATION", "reason_code": "RC"},
    ]
    merged = merge_violations_by_invariant_id(legacy, registry)
    by_id = {v["invariant_id"]: v for v in merged}
    assert by_id["INV-ZONE-002"]["status"] == "VIOLATION"
    assert by_id["INV-ZONE-002"].get("reason_code") == "RC"
    assert by_id["INV-X"]["status"] == "VIOLATION"


def test_migrated_invariants_produced_by_runtime() -> None:
    """Key invariant IDs (INV-ZONE-002, INV-STAB-BIOCHEM-001, INV-CRIT-004, INV-COAG-FILL-001)
    are produced by invariants_runtime when _finalize_step runs on ACCEPTED steps."""
    root = _repo_root()
    reg_path = root / "policy/invariants/invariant_registry.v1.0.yaml"
    if not reg_path.exists():
        pytest.skip("invariant_registry.v1.0.yaml not found")
    env = CoreEnv()
    initial = {
        "system": {"now_s": 0, "downtime_active": False},
        "agents": [
            {"agent_id": "A_PREAN", "zone_id": "Z_CENTRIFUGE_BAY"},
            {"agent_id": "A_ANALYTICS", "zone_id": "Z_ANALYZER_HALL_A"},
        ],
        "specimens": [
            {
                "specimen_id": "S1",
                "panel_id": "BIOCHEM_PANEL_CORE",
                "collection_ts_s": 0,
                "separated_ts_s": 100,
                "temp_band": "AMBIENT_20_25",
                "status": "accepted",
            },
        ],
        "tokens": [],
    }
    env.reset(initial, deterministic=True, rng_seed=42)
    # CENTRIFUGE_START with agent in device zone => INV-ZONE-002:PASS from runtime
    event = {
        "event_id": "e1",
        "t_s": 200,
        "agent_id": "A_PREAN",
        "action_type": "CENTRIFUGE_START",
        "args": {"device_id": "DEV_CENTRIFUGE_BANK_01", "specimen_ids": ["S1"]},
        "reason_code": None,
        "token_refs": [],
    }
    result = env.step(event)
    assert result["status"] == "ACCEPTED"
    violations = result.get("violations") or []
    inv_zone_002 = [v for v in violations if v.get("invariant_id") == "INV-ZONE-002"]
    assert len(inv_zone_002) == 1
    assert inv_zone_002[0]["status"] == "PASS"

    # START_RUN with agent in device zone and stability ok => INV-STAB-BIOCHEM-001:PASS
    event2 = {
        "event_id": "e2",
        "t_s": 300,
        "agent_id": "A_ANALYTICS",
        "action_type": "START_RUN",
        "args": {
            "device_id": "DEV_CHEM_A_01",
            "run_id": "R1",
            "specimen_ids": ["S1"],
        },
        "reason_code": None,
        "token_refs": [],
    }
    result2 = env.step(event2)
    assert result2["status"] == "ACCEPTED"
    violations2 = result2.get("violations") or []
    inv_stab = [v for v in violations2 if v.get("invariant_id") == "INV-STAB-BIOCHEM-001"]
    assert len(inv_stab) == 1
    assert inv_stab[0]["status"] == "PASS"
