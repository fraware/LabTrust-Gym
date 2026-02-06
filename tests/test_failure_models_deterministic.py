"""
Deterministic tests for failure physics v0.1: maintenance and reagent stockout.

- Maintenance window: START_RUN during window is BLOCKED with RC_DEVICE_MAINT.
- Reagent stockout: insufficient reagent blocks START_RUN with RC_REAGENT_STOCKOUT.
Policy-driven and seeded for reproducibility.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.engine.catalogue_runtime import (
    RC_REAGENT_STOCKOUT,
    get_panel_reagent_requirement,
    load_reagent_policy,
)
from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.engine.devices import (
    DeviceStore,
    load_equipment_registry,
    load_failure_models,
)


def _repo_root() -> Path:
    from labtrust_gym.config import get_repo_root

    return Path(get_repo_root())


def _minimal_state_with_policy(
    timing_mode: str = "simulated",
    reagent_initial_stock: dict | None = None,
) -> dict:
    root = _repo_root()
    eq_path = root / "policy" / "equipment" / "equipment_registry.v0.1.yaml"
    registry = load_equipment_registry(eq_path) if eq_path.exists() else {}
    state = {
        "effective_policy": {},
        "agents": [{"agent_id": "A_OPS_0", "zone_id": "analyzer_hall_A"}],
        "zone_layout": {
            "zones": [{"zone_id": "analyzer_hall_A"}],
            "graph_edges": [],
            "doors": [],
            "device_placement": [
                {"device_id": "DEV_CHEM_A_01", "zone_id": "analyzer_hall_A"},
            ],
        },
        "specimens": [
            {
                "specimen_id": "S1",
                "patient_identifiers_hash": "pid:1",
                "collection_ts_s": 0,
                "arrival_ts_s": 0,
                "panel_id": "BIOCHEM_PANEL_CORE",
                "container_type": "SERUM_SST",
                "specimen_type": "SERUM",
                "separated_ts_s": 10,
                "temp_band": "AMBIENT_20_25",
                "status": "aliquoted",
            }
        ],
        "tokens": [],
        "audit_fault_injection": None,
        "tool_registry": {},
        "policy_root": str(root),
        "timing_mode": timing_mode,
    }
    if registry:
        state["effective_policy"] = {"equipment_registry": registry}
    if reagent_initial_stock is not None:
        state["reagent_initial_stock"] = reagent_initial_stock
    return state


@pytest.mark.determinism
def test_maintenance_blocks_start_run_with_rc_device_maint() -> None:
    """During maintenance window, START_RUN on that device is BLOCKED with RC_DEVICE_MAINT."""
    root = _repo_root()
    fm_path = root / "policy" / "equipment" / "failure_models.v0.1.yaml"
    eq_path = root / "policy" / "equipment" / "equipment_registry.v0.1.yaml"
    if not fm_path.exists():
        pytest.skip("failure_models.v0.1.yaml not found")
    failure_models = load_failure_models(fm_path)
    registry = load_equipment_registry(eq_path) if eq_path.exists() else {}
    store = DeviceStore(registry=registry, rng=None, failure_models=failure_models)
    store.set_known_devices(["DEV_CHEM_A_01"])
    store.apply_maintenance(150)
    assert store.device_state("DEV_CHEM_A_01") == "MAINT"
    assert store.device_block_reason("DEV_CHEM_A_01") == "MAINT"
    assert store.can_start_run("DEV_CHEM_A_01") is False

    env = CoreEnv()
    state = _minimal_state_with_policy(timing_mode="simulated")
    env.reset(state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 150,
        "agent_id": "A_OPS_0",
        "action_type": "START_RUN",
        "args": {
            "device_id": "DEV_CHEM_A_01",
            "run_id": "R1",
            "specimen_ids": ["S1"],
        },
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == "RC_DEVICE_MAINT"


@pytest.mark.determinism
def test_reagent_stockout_blocks_start_run_with_rc_reagent_stockout() -> None:
    """When reagent stock is below panel requirement, START_RUN is BLOCKED with RC_REAGENT_STOCKOUT."""
    root = _repo_root()
    rp_path = root / "policy" / "reagents" / "reagent_policy.v0.1.yaml"
    if not rp_path.exists():
        pytest.skip("reagent_policy.v0.1.yaml not found")
    policy = load_reagent_policy(rp_path)
    req = get_panel_reagent_requirement(policy, "BIOCHEM_PANEL_CORE")
    assert req is not None
    reagent_id, qty, _ = req
    state = _minimal_state_with_policy(
        timing_mode="explicit",
        reagent_initial_stock={reagent_id: qty - 1},
    )
    env = CoreEnv()
    env.reset(state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 20,
        "agent_id": "A_OPS_0",
        "action_type": "START_RUN",
        "args": {
            "device_id": "DEV_CHEM_A_01",
            "run_id": "R1",
            "specimen_ids": ["S1"],
        },
    }
    result = env.step(event)
    assert result.get("status") == "BLOCKED"
    assert result.get("blocked_reason_code") == RC_REAGENT_STOCKOUT


@pytest.mark.determinism
def test_sufficient_reagent_allows_start_run() -> None:
    """When reagent stock meets panel requirement, START_RUN can be ACCEPTED (no RC_REAGENT_STOCKOUT)."""
    root = _repo_root()
    rp_path = root / "policy" / "reagents" / "reagent_policy.v0.1.yaml"
    if not rp_path.exists():
        pytest.skip("reagent_policy.v0.1.yaml not found")
    policy = load_reagent_policy(rp_path)
    req = get_panel_reagent_requirement(policy, "BIOCHEM_PANEL_CORE")
    assert req is not None
    rid, qty, _ = req
    state = _minimal_state_with_policy(
        timing_mode="explicit",
        reagent_initial_stock={rid: qty},
    )
    env = CoreEnv()
    env.reset(state, deterministic=True, rng_seed=42)
    event = {
        "t_s": 20,
        "agent_id": "A_OPS_0",
        "action_type": "START_RUN",
        "args": {
            "device_id": "DEV_CHEM_A_01",
            "run_id": "R1",
            "specimen_ids": ["S1"],
        },
    }
    result = env.step(event)
    assert result.get("blocked_reason_code") != RC_REAGENT_STOCKOUT
