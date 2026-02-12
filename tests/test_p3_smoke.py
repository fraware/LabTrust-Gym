"""Smoke test for p3: structured output retry and llm_tracer."""
from labtrust_gym.baselines.llm.structured_output_retry import (
    normalize_to_action_proposal,
    parse_and_normalize_raw,
)
from labtrust_gym.baselines.llm.llm_tracer import get_llm_tracer, LLMTracer


def test_normalize_to_action_proposal():
    p = {"action_type": "MOVE", "args": {"from_zone": "A", "to_zone": "B"}}
    n = normalize_to_action_proposal(p)
    assert n["action_type"] == "MOVE"
    assert n["args"] == {"from_zone": "A", "to_zone": "B"}
    assert "rationale" in n


def test_parse_and_normalize_raw():
    raw = ' text {"action_type": "NOOP", "args": {}} tail '
    out = parse_and_normalize_raw(raw)
    assert out["action_type"] == "NOOP"


def test_get_llm_tracer():
    t = get_llm_tracer()
    assert t is None or isinstance(t, LLMTracer)
