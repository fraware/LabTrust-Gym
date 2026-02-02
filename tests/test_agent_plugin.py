"""
Tests for external agent plugin: loader (module:Class / module:function) and eval-agent output (results.v0.2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.baselines.agent_api import (
    load_agent,
    wrap_agent_for_runner,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_load_agent_module_class() -> None:
    """Load agent from module:ClassName; returns instance."""
    repo = _repo_root()
    agent = load_agent("examples.external_agent_demo:SafeNoOpAgent", repo_root=repo)
    assert agent is not None
    assert hasattr(agent, "act")
    assert hasattr(agent, "reset")
    out = agent.act({})
    assert out in (0, 1)


def test_load_agent_module_function() -> None:
    """Load agent from module:function_name (factory); returns result of function()."""
    agent = load_agent("examples.external_agent_demo:create_safe_noop_agent")
    assert agent is not None
    assert hasattr(agent, "act")
    out = agent.act({"log_frozen": 0})
    assert out in (0, 1)


def test_load_agent_invalid_format() -> None:
    """Invalid spec format raises ValueError."""
    with pytest.raises(ValueError, match="Invalid agent spec"):
        load_agent("no_colon")
    with pytest.raises(ValueError, match="Invalid agent spec"):
        load_agent("")
    with pytest.raises(ValueError, match="Invalid agent spec"):
        load_agent(":no_module")


def test_load_agent_module_not_found() -> None:
    """Missing module raises ModuleNotFoundError."""
    with pytest.raises(ModuleNotFoundError, match="not found"):
        load_agent("nonexistent.module.path:SomeClass")


def test_load_agent_attr_not_found() -> None:
    """Module without the requested class/function raises AttributeError."""
    repo = _repo_root()
    with pytest.raises(AttributeError, match="has no attribute"):
        load_agent("examples.external_agent_demo:NonexistentClass", repo_root=repo)


def test_wrap_agent_for_runner() -> None:
    """Wrapped agent has act(obs, agent_id) -> (idx, info, meta)."""
    repo = _repo_root()
    agent = load_agent("examples.external_agent_demo:SafeNoOpAgent", repo_root=repo)
    wrapped = wrap_agent_for_runner(agent)
    wrapped.reset(42, None, None, "explicit")
    idx, info, meta = wrapped.act({"log_frozen": 0}, "ops_0")
    assert isinstance(idx, int)
    assert idx in (0, 1)
    assert isinstance(info, dict)
    assert isinstance(meta, dict)


def test_eval_agent_produces_valid_results_schema(tmp_path: Path) -> None:
    """eval-agent produces results.json that validates against results.v0.2 for 1–2 episodes."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.benchmarks.summarize import validate_results_v02
    from labtrust_gym.cli.eval_agent import run_eval_agent

    repo = _repo_root()
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")
    out_path = tmp_path / "results.json"
    run_eval_agent(
        task="TaskA",
        episodes=2,
        agent_spec="examples.external_agent_demo:SafeNoOpAgent",
        out_path=out_path,
        seed=9999,
        repo_root=repo,
    )
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data.get("schema_version") == "0.2"
    assert data.get("task") == "TaskA"
    assert isinstance(data.get("episodes"), list)
    assert len(data["episodes"]) == 2
    schema_path = repo / "policy" / "schemas" / "results.v0.2.schema.json"
    if schema_path.exists():
        errors = validate_results_v02(data, schema_path=schema_path)
        assert errors == [], f"results.v0.2 validation errors: {errors}"
