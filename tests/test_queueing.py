"""
Tests for per-device queue: STAT insertion, ordering, queue_head, START_RUN consume.
"""

from __future__ import annotations

import pytest

from labtrust_gym.engine.queueing import (
    DeviceQueue,
    DeviceQueueItem,
    PRIORITY_RANK,
    QueueStore,
)


def test_priority_rank() -> None:
    assert PRIORITY_RANK["STAT"] == 0
    assert PRIORITY_RANK["URGENT"] == 1
    assert PRIORITY_RANK["ROUTINE"] == 2


def test_stat_insertion_places_stat_before_routine() -> None:
    q = DeviceQueue(device_id="DEV_A")
    q.enqueue("S1", "ROUTINE", 100, "A1", None)
    q.enqueue("S2", "STAT", 105, "A1", None)
    assert q.head_work_id() == "S2"
    assert q.consume_head() == "S2"
    assert q.head_work_id() == "S1"


def test_stable_ordering_same_priority_tie_break() -> None:
    q = DeviceQueue(device_id="DEV_A")
    q.enqueue("S1", "ROUTINE", 100, "A1", None)
    q.enqueue("S2", "ROUTINE", 100, "A1", None)
    q.enqueue("S3", "ROUTINE", 100, "A1", None)
    # Order of insertion (tie_break) determines order when priority and ts equal
    assert q.consume_head() == "S1"
    assert q.consume_head() == "S2"
    assert q.consume_head() == "S3"
    assert q.consume_head() is None


def test_ordering_primary_priority_then_ts() -> None:
    q = DeviceQueue(device_id="DEV_A")
    q.enqueue("S1", "URGENT", 200, "A1", None)
    q.enqueue("S2", "ROUTINE", 100, "A1", None)
    q.enqueue("S3", "STAT", 300, "A1", None)
    assert q.head_work_id() == "S3"
    assert q.consume_head() == "S3"
    assert q.head_work_id() == "S1"
    assert q.consume_head() == "S1"
    assert q.head_work_id() == "S2"


def test_queue_store_unknown_device() -> None:
    store = QueueStore()
    store.set_known_devices(["DEV_CHEM_A_01"])
    assert store.is_known_device("DEV_CHEM_A_01") is True
    assert store.is_known_device("UNKNOWN_DEV") is False
    ok = store.enqueue(
        "UNKNOWN_DEV", "S1", "ROUTINE", 0, "A1", None
    )
    assert ok is False
    assert store.queue_head("UNKNOWN_DEV") is None


def test_queue_store_enqueue_and_head() -> None:
    store = QueueStore()
    store.set_known_devices(["DEV_CHEM_A_01"])
    store.enqueue(
        "DEV_CHEM_A_01", "S1", "ROUTINE", 700, "A_ANALYTICS", None
    )
    store.enqueue(
        "DEV_CHEM_A_01", "S2", "STAT", 705, "A_ANALYTICS", None
    )
    assert store.queue_head("DEV_CHEM_A_01") == "S2"
    assert store.consume_head("DEV_CHEM_A_01") == "S2"
    assert store.queue_head("DEV_CHEM_A_01") == "S1"


def test_device_queue_item_ordering() -> None:
    a = DeviceQueueItem("A", "ROUTINE", 10, "agent", None, tie_break=0)
    b = DeviceQueueItem("B", "STAT", 20, "agent", None, tie_break=1)
    assert b < a
    c = DeviceQueueItem("C", "ROUTINE", 10, "agent", None, tie_break=1)
    assert a < c


def test_start_run_consumes_head_integration() -> None:
    """Integration: CoreEnv START_RUN with device_id and no specimen_ids consumes queue head."""
    from labtrust_gym.engine.core_env import CoreEnv

    env = CoreEnv()
    env.reset(
        {
            "system": {"now_s": 0, "downtime_active": False},
            "agents": [
                {"agent_id": "A_ANALYTICS", "zone_id": "Z_ANALYZER_HALL_A"},
            ],
            "specimens": [
                {"specimen_id": "S1", "collection_ts_s": 0, "panel_id": "BIOCHEM_PANEL_CORE"},
            ],
            "tokens": [],
        },
        deterministic=True,
        rng_seed=42,
    )
    # Queue S1 on device
    env.step({
        "event_id": "e1", "t_s": 100, "agent_id": "A_ANALYTICS",
        "action_type": "QUEUE_RUN",
        "args": {"device_id": "DEV_CHEM_A_01", "accession_ids": ["S1"], "priority": "ROUTINE"},
        "reason_code": None, "token_refs": [],
    })
    assert env.query("queue_head(DEV_CHEM_A_01)") == "S1"
    # START_RUN with device_id only: should consume S1
    out = env.step({
        "event_id": "e2", "t_s": 110, "agent_id": "A_ANALYTICS",
        "action_type": "START_RUN",
        "args": {"device_id": "DEV_CHEM_A_01", "run_id": "R1"},
        "reason_code": None, "token_refs": [],
    })
    assert out["status"] == "ACCEPTED"
    assert env.query("queue_head(DEV_CHEM_A_01)") is None
