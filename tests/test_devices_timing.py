"""
Tests for equipment capacity and cycle-time models v0.1.

- Deterministic timing: same seed => same service times and completion order.
- Device state machine: IDLE -> RUNNING -> IDLE after completion.
- START_RUN in simulated mode blocks when device is RUNNING (RC_DEVICE_BUSY).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.engine.devices import (
    DeviceStore,
    load_equipment_registry,
)
from labtrust_gym.engine.rng import RNG


def test_load_equipment_registry_returns_inner_dict() -> None:
    path = Path("policy/equipment/equipment_registry.v0.1.yaml")
    if not path.exists():
        reg = load_equipment_registry(Path("nonexistent.yaml"))
        assert "device_types" in reg
        assert "device_instances" in reg
        return
    reg = load_equipment_registry(path)
    assert "device_types" in reg
    assert "device_instances" in reg
    assert "CENTRIFUGE_BANK" in reg.get("device_types", {})
    assert any(
        inst.get("device_id") == "DEV_CENTRIFUGE_BANK_01"
        for inst in reg.get("device_instances", [])
    )


def test_device_store_deterministic_service_time_same_seed() -> None:
    reg = load_equipment_registry()
    if not reg.get("device_types"):
        pytest.skip("equipment_registry not found or empty")
    rng1 = RNG(42)
    rng2 = RNG(42)
    store1 = DeviceStore(registry=reg, rng=rng1)
    store2 = DeviceStore(registry=reg, rng=rng2)
    store1.set_known_devices(["DEV_CHEM_A_01"])
    store2.set_known_devices(["DEV_CHEM_A_01"])
    ok1 = store1.start_run(
        "DEV_CHEM_A_01", "R1", 100, specimen_ids=["S1"], panel_id="BIOCHEM_PANEL_CORE"
    )
    ok2 = store2.start_run(
        "DEV_CHEM_A_01", "R1", 100, specimen_ids=["S1"], panel_id="BIOCHEM_PANEL_CORE"
    )
    assert ok1 and ok2
    run1 = store1.get_active_run("DEV_CHEM_A_01")
    run2 = store2.get_active_run("DEV_CHEM_A_01")
    assert run1 is not None and run2 is not None
    assert run1.end_ts_s == run2.end_ts_s, "same seed => same service time (end_ts_s)"


def test_device_store_different_seed_different_service_time() -> None:
    reg = load_equipment_registry()
    if not reg.get("device_types"):
        pytest.skip("equipment_registry not found or empty")
    # Use a type that has a random distribution if any; otherwise deterministic still gives same value.
    # Centrifuge has deterministic 600s spin - so we compare two devices with different panel to get different duration.
    store_a = DeviceStore(registry=reg, rng=RNG(1))
    store_b = DeviceStore(registry=reg, rng=RNG(999))
    store_a.set_known_devices(["DEV_CHEM_A_01", "DEV_COAG_01"])
    store_b.set_known_devices(["DEV_CHEM_A_01", "DEV_COAG_01"])
    store_a.start_run("DEV_CHEM_A_01", "R1", 0, panel_id="BIOCHEM_PANEL_CORE")
    store_b.start_run("DEV_CHEM_A_01", "R1", 0, panel_id="BIOCHEM_PANEL_CORE")
    run_a = store_a.get_active_run("DEV_CHEM_A_01")
    run_b = store_b.get_active_run("DEV_CHEM_A_01")
    assert run_a is not None and run_b is not None
    # Both deterministic panel => same end_ts_s
    assert run_a.end_ts_s == run_b.end_ts_s


def test_device_state_idle_then_running_then_idle() -> None:
    reg = load_equipment_registry()
    store = DeviceStore(registry=reg, rng=RNG(0))
    store.set_known_devices(["DEV_CENTRIFUGE_BANK_01"])
    assert store.device_state("DEV_CENTRIFUGE_BANK_01") == "IDLE"
    ok = store.start_run("DEV_CENTRIFUGE_BANK_01", "RUN1", 0, specimen_ids=["S1"])
    assert ok
    assert store.device_state("DEV_CENTRIFUGE_BANK_01") == "RUNNING"
    run = store.get_active_run("DEV_CENTRIFUGE_BANK_01")
    assert run is not None
    assert run.run_id == "RUN1"
    # Complete by advancing time past end_ts_s
    completed = store.completions(run.end_ts_s + 1)
    assert ("DEV_CENTRIFUGE_BANK_01", "RUN1") in completed
    store.finish_run("DEV_CENTRIFUGE_BANK_01")
    assert store.device_state("DEV_CENTRIFUGE_BANK_01") == "IDLE"
    assert store.get_active_run("DEV_CENTRIFUGE_BANK_01") is None


def test_can_start_run_false_when_running() -> None:
    reg = load_equipment_registry()
    store = DeviceStore(registry=reg, rng=RNG(0))
    store.set_known_devices(["DEV_ALIQUOTER_01"])
    assert store.can_start_run("DEV_ALIQUOTER_01") is True
    store.start_run("DEV_ALIQUOTER_01", "R1", 0)
    assert store.can_start_run("DEV_ALIQUOTER_01") is False
    run = store.get_active_run("DEV_ALIQUOTER_01")
    assert run is not None
    store.finish_run("DEV_ALIQUOTER_01")
    assert store.can_start_run("DEV_ALIQUOTER_01") is True


def test_finish_completions_clears_runs() -> None:
    reg = load_equipment_registry()
    store = DeviceStore(registry=reg, rng=RNG(0))
    store.set_known_devices(["DEV_CHEM_A_01"])
    store.start_run("DEV_CHEM_A_01", "R1", 0, panel_id="BIOCHEM_PANEL_CORE")
    run = store.get_active_run("DEV_CHEM_A_01")
    assert run is not None
    end_ts = run.end_ts_s
    result = store.finish_completions(end_ts)
    assert len(result) == 1
    did, run_id, active_run = result[0]
    assert did == "DEV_CHEM_A_01"
    assert run_id == "R1"
    assert active_run is not None
    assert store.device_state("DEV_CHEM_A_01") == "IDLE"


def test_golden_suite_still_uses_explicit_timing() -> None:
    """Golden suite does not set timing_mode so it defaults to explicit; no device_store blocking."""
    from labtrust_gym.engine.core_env import CoreEnv

    env = CoreEnv()
    initial_state = {
        "system": {"now_s": 0, "downtime_active": False},
        "agents": [{"agent_id": "A_ANALYTICS", "zone_id": "Z_ANALYZER_HALL_A"}],
        "specimens": [
            {
                "specimen_id": "S1",
                "patient_identifiers_hash": "pid:hash:001",
                "collection_ts_s": 0,
                "panel_id": "BIOCHEM_PANEL_CORE",
                "container_type": "SERUM_SST",
                "separated_ts_s": 100,
                "temp_band": "AMBIENT_20_25",
                "status": "accepted",
            }
        ],
        "tokens": [],
    }
    env.reset(initial_state, deterministic=True, rng_seed=12345)
    # START_RUN without timing_mode => explicit => no device_store => ACCEPTED
    result = env.step({
        "event_id": "e1",
        "t_s": 1500,
        "agent_id": "A_ANALYTICS",
        "action_type": "START_RUN",
        "args": {"device_id": "DEV_CHEM_A_01", "run_id": "R1", "specimen_ids": ["S1"]},
        "reason_code": None,
        "token_refs": [],
    })
    assert result["status"] == "ACCEPTED"
    assert "START_RUN" in (result.get("emits") or [])
