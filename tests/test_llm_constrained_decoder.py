"""
Constrained action decoder: illegal action rejected/NOOP with reason; missing rationale rejected; deterministic.
TaskF: signature/RBAC attack containment with LLM baseline.
"""

from pathlib import Path

import pytest

from labtrust_gym.baselines.llm.decoder import (
    MISSING_RATIONALE,
    decode_constrained,
    validate_schema_returns_errors,
)
from labtrust_gym.baselines.llm.agent import (
    DeterministicConstrainedBackend,
    LLMAgentWithShield,
    load_llm_action_schema_v02,
)
from labtrust_gym.engine.rbac import get_allowed_actions, load_rbac_policy


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_decode_constrained_illegal_action_rejected() -> None:
    """Proposed action_type not in allowed_actions -> rejected, NOOP, RBAC_ACTION_DENY."""
    schema = load_llm_action_schema_v02(_repo_root() / "policy/llm/llm_action.schema.v0.2.json")
    if not schema:
        pytest.skip("llm_action.schema.v0.2.json not found")
    policy_summary = {"allowed_actions": ["NOOP", "TICK"], "agent_zone": None}
    candidate = {
        "action_type": "RELEASE_RESULT",
        "args": {"result_id": "R1"},
        "rationale": "want to release",
    }
    action, rejected, reason = decode_constrained(
        candidate, policy_summary, schema, validate_schema_returns_errors, require_rationale=True
    )
    assert rejected is True
    assert reason == "RBAC_ACTION_DENY"
    assert action.get("action_type") == "NOOP"


def test_decode_constrained_missing_rationale_rejected() -> None:
    """Missing or empty rationale -> rejected, NOOP, MISSING_RATIONALE."""
    schema = load_llm_action_schema_v02(_repo_root() / "policy/llm/llm_action.schema.v0.2.json")
    if not schema:
        pytest.skip("llm_action.schema.v0.2.json not found")
    policy_summary = {"allowed_actions": ["NOOP", "TICK"]}
    candidate = {"action_type": "TICK", "args": {}}
    action, rejected, reason = decode_constrained(
        candidate, policy_summary, schema, validate_schema_returns_errors, require_rationale=True
    )
    assert rejected is True
    assert reason == MISSING_RATIONALE
    assert action.get("action_type") == "NOOP"

    candidate["rationale"] = ""
    action2, rejected2, reason2 = decode_constrained(
        candidate, policy_summary, schema, validate_schema_returns_errors, require_rationale=True
    )
    assert rejected2 is True
    assert reason2 == MISSING_RATIONALE


def test_decode_constrained_valid_passes() -> None:
    """Valid action with rationale in allowed_actions -> pass."""
    schema = load_llm_action_schema_v02(_repo_root() / "policy/llm/llm_action.schema.v0.2.json")
    if not schema:
        pytest.skip("llm_action.schema.v0.2.json not found")
    policy_summary = {"allowed_actions": ["NOOP", "TICK"]}
    candidate = {"action_type": "TICK", "args": {}, "rationale": "advance time"}
    action, rejected, reason = decode_constrained(
        candidate, policy_summary, schema, validate_schema_returns_errors, require_rationale=True
    )
    assert rejected is False
    assert reason is None
    assert action.get("action_type") == "TICK"
    assert action.get("rationale") == "advance time"


def test_deterministic_constrained_backend_same_seed_same_sequence() -> None:
    """DeterministicConstrainedBackend: same seed => same action sequence for same allowed_actions."""
    import json
    backend = DeterministicConstrainedBackend(seed=12345, default_action_type="NOOP")
    allowed = ["NOOP", "TICK", "QUEUE_RUN"]
    user = json.dumps({"allowed_actions": allowed}, sort_keys=True)
    messages = [{"role": "user", "content": user}]
    out1 = backend.generate(messages)
    out2 = backend.generate(messages)
    d1 = json.loads(out1)
    d2 = json.loads(out2)
    assert d1["action_type"] == d2["action_type"]
    assert d1["rationale"] == "deterministic baseline"
    assert d1["action_type"] in allowed


def test_deterministic_constrained_backend_fixed_seed_reproducible() -> None:
    """Two backends with same seed produce same sequence of actions."""
    import json
    allowed = ["NOOP", "TICK"]
    user = json.dumps({"allowed_actions": allowed}, sort_keys=True)
    msg = [{"role": "user", "content": user}]
    b1 = DeterministicConstrainedBackend(seed=99, default_action_type="NOOP")
    b2 = DeterministicConstrainedBackend(seed=99, default_action_type="NOOP")
    actions1 = [json.loads(b1.generate(msg))["action_type"] for _ in range(5)]
    actions2 = [json.loads(b2.generate(msg))["action_type"] for _ in range(5)]
    assert actions1 == actions2


def test_task_f_llm_baseline_rbac_containment() -> None:
    """TaskF with use_llm_safe_v1_ops: LLM baseline uses DeterministicConstrainedBackend; RBAC/insider containment still demonstrated."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    import tempfile
    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        r = run_benchmark(
            "TaskF",
            num_episodes=2,
            base_seed=99,
            out_path=out,
            repo_root=root,
            use_llm_safe_v1_ops=True,
        )
    assert len(r.get("episodes", [])) == 2
    for ep in r["episodes"]:
        metrics = ep.get("metrics", {})
        assert "fraction_of_attacks_contained" in metrics or "throughput" in metrics
