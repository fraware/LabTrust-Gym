"""
Blackboard log: replay determinism and head_hash stability.
Same events appended in order => identical replay and head_hash across runs.
"""

from __future__ import annotations

import hashlib
import json

from labtrust_gym.coordination.blackboard import BlackboardLog


def test_blackboard_append_and_replay() -> None:
    """Append events; replay returns same sequence of dicts."""
    log = BlackboardLog()
    log.append(0, 0, "QUEUE_HEAD", {"device_id": "D1", "queue_head_work_id": "W1"})
    log.append(1, 1, "AGENT_ZONE", {"agent_id": "a1", "zone_id": "Z_A"})
    replay = log.replay()
    assert len(replay) == 2
    assert replay[0]["type"] == "QUEUE_HEAD"
    assert replay[0]["payload_small"].get("device_id") == "D1"
    assert replay[1]["type"] == "AGENT_ZONE"
    assert replay[1]["id"] == 1


def test_blackboard_head_hash_deterministic() -> None:
    """Same append sequence => same head_hash (two separate logs)."""

    def make_log() -> BlackboardLog:
        l1 = BlackboardLog()
        l1.append(0, 0, "A", {"x": 1})
        l1.append(1, 1, "B", {"y": 2})
        return l1

    h1 = make_log().head_hash
    h2 = make_log().head_hash
    assert h1 == h2
    assert len(h1) == 24


def test_blackboard_replay_determinism() -> None:
    """Replay is deterministic: same canonical JSON across runs."""
    log = BlackboardLog()
    for t in range(10):
        log.append(t, t, "EVT", {"step": t, "payload": f"p{t}"})
    replay1 = log.replay()
    replay2 = log.replay()
    assert replay1 == replay2
    canonical = json.dumps(replay1, sort_keys=True)
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert len(h) == 64


def test_blackboard_events_since() -> None:
    """events_since(after_id) returns only events with id > after_id."""
    log = BlackboardLog()
    log.append(0, 0, "A", {})
    log.append(1, 1, "B", {})
    log.append(2, 2, "C", {})
    since0 = log.events_since(0)
    assert len(since0) == 2
    assert since0[0].id == 1 and since0[1].id == 2
    since1 = log.events_since(1)
    assert len(since1) == 1
    assert since1[0].id == 2
    since2 = log.events_since(2)
    assert len(since2) == 0
