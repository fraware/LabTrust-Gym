"""
Handoff protocol: HandoffEvent creation, ACK within T steps, escalation on missing ACK.
"""

from __future__ import annotations

from labtrust_gym.baselines.coordination.hierarchical.handoff import (
    HUB_REGION_ID,
    HandoffEvent,
    HandoffProtocol,
)


def test_handoff_create_and_ack() -> None:
    proto = HandoffProtocol(ack_deadline_steps=5)
    proto.create_handoff("W1", "D1", HUB_REGION_ID, "R_0", "Z_A", t=0, priority=1)
    assert proto.has_pending("W1", "D1", "R_0")
    assert proto.ack("W1", "D1", t=1) is True
    assert proto.has_pending("W1", "D1", "R_0") is False
    assert proto.ack("W1", "D1", t=2) is False


def test_handoff_escalation_on_timeout() -> None:
    proto = HandoffProtocol(ack_deadline_steps=3)
    proto.create_handoff("W2", "D2", HUB_REGION_ID, "R_1", "Z_B", t=0, priority=0)
    still, escalated = proto.tick(1)
    assert len(escalated) == 0
    assert len(still) == 1
    still, escalated = proto.tick(4)
    assert len(escalated) == 1
    assert escalated[0].work_id == "W2" and escalated[0].device_id == "D2"
    assert len(still) == 0


def test_handoff_ack_before_deadline_no_escalation() -> None:
    proto = HandoffProtocol(ack_deadline_steps=10)
    proto.create_handoff("W3", "D3", "R_0", "R_1", "Z_C", t=0, priority=2)
    proto.ack("W3", "D3", t=2)
    still, escalated = proto.tick(5)
    assert len(escalated) == 0
    assert len(still) == 0


def test_handoff_metrics() -> None:
    proto = HandoffProtocol(ack_deadline_steps=2)
    proto.create_handoff("W4", "D4", HUB_REGION_ID, "R_0", "Z_D", t=0, priority=0)
    proto.create_handoff("W5", "D5", HUB_REGION_ID, "R_0", "Z_D", t=0, priority=0)
    proto.ack("W4", "D4", t=1)
    proto.tick(5)
    m = proto.get_metrics()
    assert m["cross_region_handoffs"] == 2
    assert m["handoff_ack_count"] == 1
    assert m["escalations"] == 1
    assert m["handoff_fail_rate"] == 0.5


def test_handoff_event_is_expired() -> None:
    ev = HandoffEvent(
        work_id="W",
        device_id="D",
        from_region="HUB",
        to_region="R_0",
        zone_id="Z",
        created_t=0,
        ack_by_t=5,
    )
    assert ev.is_expired(3) is False
    assert ev.is_expired(6) is True
    ev.acked = True
    assert ev.is_expired(6) is False
