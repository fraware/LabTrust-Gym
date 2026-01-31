"""
LLM agent mock: deterministic mapping and schema validation.
"""

from pathlib import Path

import pytest

from labtrust_gym.baselines.llm.agent import (
    LLMAgent,
    MockDeterministicBackend,
    _obs_hash,
    load_action_schema,
    validate_action_against_schema,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_mock_backend_deterministic() -> None:
    """MockDeterministicBackend returns same JSON for same message."""
    import hashlib
    key = hashlib.sha256(b"x").hexdigest()[:16]
    canned = {key: {"action_type": 2, "action_info": {"device_id": "DEV_CHEM_A_01"}}}
    backend = MockDeterministicBackend(canned=canned, default_action_type=0)
    msg = [{"role": "user", "content": "x"}]
    out1 = backend.generate(msg)
    out2 = backend.generate(msg)
    assert out1 == out2
    data = __import__("json").loads(out1)
    assert data.get("action_type") == 2
    assert data.get("action_info", {}).get("device_id") == "DEV_CHEM_A_01"


def test_llm_agent_parse_and_validate() -> None:
    """LLMAgent parses JSON and validates against schema; invalid falls back to NOOP."""
    backend = MockDeterministicBackend(default_action_type=1)
    schema_path = _repo_root() / "policy/llm/action_schema.v0.1.json"
    agent = LLMAgent(backend=backend, schema_path=schema_path)
    obs = {"my_zone_idx": 1, "log_frozen": 0}
    action_idx, action_info = agent.act(obs, "ops_0")
    assert action_idx in (0, 1, 2, 3, 4, 5)
    assert isinstance(action_info, dict)


def test_action_schema_validation() -> None:
    """Valid action passes; invalid action fails schema validation."""
    schema = load_action_schema(_repo_root() / "policy/llm/action_schema.v0.1.json")
    if not schema:
        pytest.skip("policy/llm/action_schema.v0.1.json not found")
    errs = validate_action_against_schema(
        {"action_type": 0, "action_info": {}},
        schema,
    )
    assert errs == []
    errs = validate_action_against_schema(
        {"action_type": 2, "action_info": {"device_id": "DEV_CHEM_A_01", "work_id": "W1"}},
        schema,
    )
    assert errs == []
    errs = validate_action_against_schema(
        {"action_type": 99},
        schema,
    )
    assert len(errs) >= 1


def test_obs_hash_deterministic() -> None:
    """_obs_hash is deterministic for same observation."""
    obs = {"a": 1, "b": [2, 3]}
    h1 = _obs_hash(obs)
    h2 = _obs_hash(obs)
    assert h1 == h2
    obs2 = {"b": [2, 3], "a": 1}
    assert _obs_hash(obs2) == h1
