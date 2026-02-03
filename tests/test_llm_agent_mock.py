"""
LLM agent mock: deterministic mapping and schema validation.
LLM shield: determinism with fixed mock, safety (forbidden action -> shield blocks).
"""

from pathlib import Path

import pytest

from labtrust_gym.baselines.llm.agent import (
    LLMAgent,
    LLMAgentWithShield,
    MockDeterministicBackend,
    MockDeterministicBackendV2,
    _obs_hash,
    load_action_schema,
    load_llm_action_schema_v02,
    validate_action_against_schema,
    validate_llm_action_v02,
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
        {
            "action_type": 2,
            "action_info": {"device_id": "DEV_CHEM_A_01", "work_id": "W1"},
        },
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


# --- LLM v0.2 + shield: determinism and safety ---


def test_mock_backend_v2_deterministic() -> None:
    """MockDeterministicBackendV2 returns same JSON for same message (string action_type)."""
    import hashlib

    key = hashlib.sha256(b"obs_x").hexdigest()[:16]
    canned = {key: {"action_type": "TICK", "args": {}, "rationale": "test"}}
    backend = MockDeterministicBackendV2(canned=canned, default_action_type="NOOP")
    msg = [{"role": "user", "content": "obs_x"}]
    out1 = backend.generate(msg)
    out2 = backend.generate(msg)
    assert out1 == out2
    data = __import__("json").loads(out1)
    assert data.get("action_type") == "TICK"
    assert data.get("args") == {}


def test_llm_action_v02_schema_validation() -> None:
    """llm_action.schema.v0.2: valid action passes; invalid fails."""
    schema = load_llm_action_schema_v02(
        _repo_root() / "policy/llm/llm_action.schema.v0.2.json"
    )
    if not schema:
        pytest.skip("policy/llm/llm_action.schema.v0.2.json not found")
    errs = validate_llm_action_v02({"action_type": "NOOP", "args": {}}, schema)
    assert errs == []
    errs = validate_llm_action_v02(
        {"action_type": "RELEASE_RESULT", "args": {"result_id": "R1"}}, schema
    )
    assert errs == []
    errs = validate_llm_action_v02({}, schema)
    assert len(errs) >= 1


def test_llm_shield_determinism() -> None:
    """LLMAgentWithShield with fixed mock backend returns same (idx, info, meta) for same obs."""
    import hashlib
    import json
    from labtrust_gym.baselines.llm.shield import build_policy_summary
    from labtrust_gym.engine.rbac import (
        get_agent_role,
        get_allowed_actions,
        load_rbac_policy,
    )

    rbac_path = _repo_root() / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
    if not rbac_path.exists():
        pytest.skip("rbac_policy.v0.1.yaml not found")
    rbac_policy = load_rbac_policy(rbac_path)
    obs = {"my_zone_idx": 1}
    engine_id = "A_OPS_0"
    allowed = get_allowed_actions(engine_id, rbac_policy)
    role_id = get_agent_role(engine_id, rbac_policy)
    policy_summary = build_policy_summary(allowed_actions=allowed, role_id=role_id)
    citation_anchors = list(policy_summary.get("citation_anchors") or [])
    user_content = json.dumps(
        {
            "obs_hash": _obs_hash(obs),
            "allowed_actions": allowed,
            "citation_anchors": citation_anchors,
        },
        sort_keys=True,
    )
    key = hashlib.sha256(user_content.encode()).hexdigest()[:16]
    anchor = citation_anchors[0] if citation_anchors else "POLICY:RBAC:allowed_actions"
    canned = {key: {"action_type": "TICK", "args": {}, "rationale": f"{anchor} test"}}
    backend = MockDeterministicBackendV2(canned=canned, default_action_type="NOOP")
    pz_to_engine = {"ops_0": "A_OPS_0"}
    agent = LLMAgentWithShield(
        backend=backend,
        rbac_policy=rbac_policy,
        pz_to_engine=pz_to_engine,
        schema_path=_repo_root() / "policy/llm/llm_action.schema.v0.2.json",
        strict_signatures=False,
    )
    ret1 = agent.act(obs, "ops_0")
    ret2 = agent.act(obs, "ops_0")
    assert len(ret1) == 3
    assert ret1[0] == ret2[0]
    assert ret1[1] == ret2[1]
    assert ret1[2] == ret2[2]
    # LLM audit hashes in meta (step output / receipts)
    meta = ret1[2]
    assert meta.get("_prompt_hash") is not None and len(meta["_prompt_hash"]) == 64
    assert meta.get("_policy_summary_hash") is not None
    assert meta.get("_allowed_actions_hash") is not None
    assert meta.get("_decoder_version") == "v0.2"


def test_llm_shield_safety_forbidden_action() -> None:
    """Model proposes RELEASE_RESULT for A_RECEPTION -> shield blocks with RBAC_ACTION_DENY."""
    import hashlib
    import json
    from labtrust_gym.baselines.llm.shield import build_policy_summary
    from labtrust_gym.engine.rbac import (
        get_agent_role,
        get_allowed_actions,
        load_rbac_policy,
    )

    rbac_path = _repo_root() / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
    if not rbac_path.exists():
        pytest.skip("rbac_policy.v0.1.yaml not found")
    rbac_policy = load_rbac_policy(rbac_path)
    obs = {"my_zone_idx": 1}
    engine_id = "A_RECEPTION"
    allowed = get_allowed_actions(engine_id, rbac_policy)
    role_id = get_agent_role(engine_id, rbac_policy)
    policy_summary = build_policy_summary(allowed_actions=allowed, role_id=role_id)
    citation_anchors = list(policy_summary.get("citation_anchors") or [])
    user_content = json.dumps(
        {
            "obs_hash": _obs_hash(obs),
            "allowed_actions": allowed,
            "citation_anchors": citation_anchors,
        },
        sort_keys=True,
    )
    key = hashlib.sha256(user_content.encode()).hexdigest()[:16]
    anchor = citation_anchors[0] if citation_anchors else "POLICY:RBAC:allowed_actions"
    canned = {
        key: {
            "action_type": "RELEASE_RESULT",
            "args": {"result_id": "R_ANY"},
            "rationale": f"{anchor} test",
        }
    }
    backend = MockDeterministicBackendV2(canned=canned, default_action_type="NOOP")
    pz_to_engine = {"ops_0": "A_RECEPTION"}
    agent = LLMAgentWithShield(
        backend=backend,
        rbac_policy=rbac_policy,
        pz_to_engine=pz_to_engine,
        schema_path=_repo_root() / "policy/llm/llm_action.schema.v0.2.json",
        strict_signatures=False,
        use_action_proposal_schema=False,
    )
    ret = agent.act(obs, "ops_0")
    assert len(ret) == 3
    idx, info, meta = ret
    assert meta.get("_shield_filtered") is True
    assert meta.get("_shield_reason_code") == "RBAC_ACTION_DENY"
    assert info.get("action_type") == "NOOP"


def test_task_e_llm_safe_v1_runs_deterministically() -> None:
    """TaskE runs with use_llm_safe_v1_ops (mocked) and produces deterministic metrics."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    import tempfile

    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        r1 = run_benchmark(
            "TaskE",
            num_episodes=2,
            base_seed=42,
            out_path=out,
            repo_root=root,
            use_llm_safe_v1_ops=True,
        )
        r2 = run_benchmark(
            "TaskE",
            num_episodes=2,
            base_seed=42,
            out_path=Path(tmp) / "results2.json",
            repo_root=root,
            use_llm_safe_v1_ops=True,
        )
        assert len(r1.get("episodes", [])) == 2
        assert len(r2.get("episodes", [])) == 2
        for i in range(2):
            m1 = r1["episodes"][i].get("metrics", {})
            m2 = r2["episodes"][i].get("metrics", {})
            assert m1.get("throughput") == m2.get("throughput")


def test_task_f_llm_safe_v1_runs_deterministically() -> None:
    """TaskF runs with use_llm_safe_v1_ops (mocked) and produces deterministic metrics."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    import tempfile

    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        r1 = run_benchmark(
            "TaskF",
            num_episodes=2,
            base_seed=99,
            out_path=out,
            repo_root=root,
            use_llm_safe_v1_ops=True,
        )
        r2 = run_benchmark(
            "TaskF",
            num_episodes=2,
            base_seed=99,
            out_path=Path(tmp) / "results2.json",
            repo_root=root,
            use_llm_safe_v1_ops=True,
        )
        assert len(r1.get("episodes", [])) == 2
        assert len(r2.get("episodes", [])) == 2
        for i in range(2):
            m1 = r1["episodes"][i].get("metrics", {})
            m2 = r2["episodes"][i].get("metrics", {})
            assert m1.get("fraction_of_attacks_contained") == m2.get(
                "fraction_of_attacks_contained"
            )
