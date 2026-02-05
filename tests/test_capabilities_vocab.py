"""
Tests for capabilities vocabulary and tool-registry validation.

- load_capabilities_vocab returns set of capability IDs.
- validate_capabilities(registry, cap_vocab): registry capabilities must be subset of vocab.
- load_state_tool_capability_map returns state_label -> allowed_capabilities.
- get_allowed_capabilities_for_state respects state_label and default.
- Policy validation: tool registry capabilities subset of capabilities.v0.1.yaml.
"""

from pathlib import Path

import pytest

from labtrust_gym.tools.capabilities import (
    get_allowed_capabilities_for_state,
    load_capabilities_vocab,
    load_state_tool_capability_map,
    validate_capabilities,
)


def test_load_capabilities_vocab_from_repo_root() -> None:
    """Load capabilities vocabulary from repo root; returns non-empty set."""
    root = Path(__file__).resolve().parents[1]
    path = root / "policy" / "capabilities.v0.1.yaml"
    if not path.exists():
        pytest.skip("policy/capabilities.v0.1.yaml not found")
    vocab = load_capabilities_vocab(root)
    assert isinstance(vocab, set)
    assert "lims.read" in vocab
    assert "lims.write" in vocab
    assert "queue.read" in vocab
    assert "device.actuate" in vocab


def test_validate_capabilities_all_subset() -> None:
    """When all tool capabilities are in vocab, validate_capabilities returns no errors."""
    vocab = {"lims.read", "lims.write", "queue.read"}
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {"tool_id": "read_lims_v1", "capabilities": ["lims.read"]},
                {"tool_id": "write_lims_v1", "capabilities": ["lims.write"]},
                {"tool_id": "query_queue_v1", "capabilities": ["queue.read"]},
            ],
        }
    }
    errors = validate_capabilities(registry, vocab)
    assert errors == []


def test_validate_capabilities_rejects_unknown() -> None:
    """When a tool declares a capability not in vocab, validate_capabilities returns errors."""
    vocab = {"lims.read", "lims.write"}
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [
                {"tool_id": "read_lims_v1", "capabilities": ["lims.read"]},
                {"tool_id": "bad_tool", "capabilities": ["net.egress"]},
            ],
        }
    }
    errors = validate_capabilities(registry, vocab)
    assert len(errors) >= 1
    assert any("bad_tool" in e and "net.egress" in e for e in errors)


def test_validate_capabilities_empty_vocab_means_no_check() -> None:
    """Empty vocab means no subset check (backward compat)."""
    registry = {
        "tool_registry": {
            "version": "0.1",
            "tools": [{"tool_id": "foo", "capabilities": ["anything"]}],
        }
    }
    errors = validate_capabilities(registry, set())
    assert errors == []


def test_load_state_tool_capability_map_from_repo() -> None:
    """Load state_tool_capability_map from repo; returns state_label -> list of capabilities."""
    root = Path(__file__).resolve().parents[1]
    path = root / "policy" / "state_tool_capability_map.v0.1.yaml"
    if not path.exists():
        pytest.skip("policy/state_tool_capability_map.v0.1.yaml not found")
    state_map = load_state_tool_capability_map(root)
    assert isinstance(state_map, dict)
    assert "accessioning" in state_map
    assert "lims.read" in state_map["accessioning"]
    assert "default" in state_map


def test_get_allowed_capabilities_for_state() -> None:
    """get_allowed_capabilities_for_state returns state entry or default."""
    state_map = {
        "accessioning": ["lims.read", "queue.read"],
        "default": ["lims.read", "lims.write", "queue.read"],
    }
    assert get_allowed_capabilities_for_state("accessioning", state_map) == [
        "lims.read",
        "queue.read",
    ]
    assert get_allowed_capabilities_for_state("unknown_phase", state_map) == [
        "lims.read",
        "lims.write",
        "queue.read",
    ]
    assert get_allowed_capabilities_for_state(None, state_map) == [
        "lims.read",
        "lims.write",
        "queue.read",
    ]
    assert get_allowed_capabilities_for_state("x", {}) is None
