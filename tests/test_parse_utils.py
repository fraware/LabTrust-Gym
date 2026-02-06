"""
Unit tests for robust JSON parse (extract_first_json_object).

No network. Used when supports_structured_outputs=False (e.g. Ollama, vLLM).
"""

from __future__ import annotations

import json

from labtrust_gym.baselines.llm.parse_utils import extract_first_json_object


def test_extract_first_json_object_plain() -> None:
    """Plain single JSON object is returned as-is."""
    raw = '{"action_type": "NOOP", "args": {}}'
    out = extract_first_json_object(raw)
    assert out == raw
    assert json.loads(out) == {"action_type": "NOOP", "args": {}}


def test_extract_first_json_object_with_prefix() -> None:
    """Leading text is skipped; first top-level object is returned."""
    raw = 'Here is the result: {"a": 1, "b": 2} rest of output'
    out = extract_first_json_object(raw)
    assert out == '{"a": 1, "b": 2}'
    assert json.loads(out) == {"a": 1, "b": 2}


def test_extract_first_json_object_with_suffix() -> None:
    """Trailing text is ignored."""
    raw = '{"x": 42}\n\nSome explanation.'
    out = extract_first_json_object(raw)
    assert out == '{"x": 42}'


def test_extract_first_json_object_markdown_code_block() -> None:
    """JSON inside markdown code block is extracted."""
    raw = '```json\n{"action_type": "TICK", "args": {}}\n```'
    out = extract_first_json_object(raw)
    assert out is not None
    assert json.loads(out)["action_type"] == "TICK"


def test_extract_first_json_object_nested() -> None:
    """Nested braces are balanced."""
    raw = 'outer {"inner": {"deep": 1}, "arr": [1,2]} tail'
    out = extract_first_json_object(raw)
    assert out == '{"inner": {"deep": 1}, "arr": [1,2]}'
    assert json.loads(out)["inner"]["deep"] == 1


def test_extract_first_json_object_no_json() -> None:
    """No brace returns None."""
    assert extract_first_json_object("no json here") is None
    assert extract_first_json_object("") is None
    assert extract_first_json_object("   \n  ") is None


def test_extract_first_json_object_string_with_braces() -> None:
    """Braces inside strings do not end the object."""
    raw = '{"msg": "say {hello} world"}'
    out = extract_first_json_object(raw)
    assert out == raw
    assert json.loads(out)["msg"] == "say {hello} world"


def test_extract_first_json_object_action_proposal_shape() -> None:
    """Realistic ActionProposal-like payload is extracted."""
    raw = (
        "Sure. Here is the action:\n"
        '{"action_type": "NOOP", "args": {}, "reason_code": null, '
        '"token_refs": [], "rationale": "waiting", "confidence": 0.9, "safety_notes": ""}\n'
        "Let me know if you need more."
    )
    out = extract_first_json_object(raw)
    assert out is not None
    obj = json.loads(out)
    assert obj["action_type"] == "NOOP"
    assert obj["rationale"] == "waiting"
    assert obj["confidence"] == 0.9
