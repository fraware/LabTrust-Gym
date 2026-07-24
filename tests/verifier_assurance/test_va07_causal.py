"""LT-VA-07 causal graph and hashchain compatibility tests."""

from __future__ import annotations

import pytest

from labtrust_gym.engine.audit_log import AuditLog
from labtrust_gym.verifier_assurance.causal.graph import (
    CAUSAL_MODEL_NOTE,
    CausalGraphError,
    append_with_causal,
    attach_causal_fields,
    validate_causal_graph,
)


def test_backward_compatible_events_without_causal() -> None:
    event = {"event_id": "e1", "action_type": "TICK"}
    enriched = attach_causal_fields(event, None)
    assert enriched["_causal_model_note"] == CAUSAL_MODEL_NOTE
    audit = AuditLog()
    hc, broken, body = append_with_causal(audit, event, None)
    assert broken is False
    assert hc["length"] == 1
    assert "parent_event_ids" not in body or body.get("parent_event_ids") is None


def test_graph_validation_and_cycles() -> None:
    events = [
        attach_causal_fields(
            {"event_id": "e1", "action_type": "A"},
            {"parent_event_ids": [], "downstream_event_ids": ["e2"]},
        ),
        attach_causal_fields(
            {"event_id": "e2", "action_type": "B"},
            {"parent_event_ids": ["e1"]},
        ),
    ]
    assert validate_causal_graph(events)["valid"] is True
    cyclic = [
        attach_causal_fields({"event_id": "e1"}, {"downstream_event_ids": ["e2"]}),
        attach_causal_fields({"event_id": "e2"}, {"downstream_event_ids": ["e1"]}),
    ]
    with pytest.raises(CausalGraphError):
        validate_causal_graph(cyclic)


def test_hashchain_still_verifies_with_causal_fields() -> None:
    audit = AuditLog()
    events = []
    for i in range(3):
        _, _, body = append_with_causal(
            audit,
            {"event_id": f"e{i}", "action_type": "A"},
            {"parent_event_ids": [f"e{i-1}"] if i else [], "responsible_principal": "ops_0"},
        )
        events.append(body)
    assert audit.length == 3
    assert audit.head_hash
    assert CAUSAL_MODEL_NOTE in events[0]["_causal_model_note"]
