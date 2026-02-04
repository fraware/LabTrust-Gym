"""
Prompt registry and prompt fingerprinting.

- prompt registry validates (validate-policy)
- prompt_fingerprint stable across runs
- changing prompt version changes fingerprint
- LLM_DECISION includes prompt_id, prompt_version, prompt_fingerprint
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.policy.prompt_registry import (
    DEFAULT_PROMPT_ID,
    DEFAULT_PROMPT_VERSION,
    compute_prompt_fingerprint,
    get_prompt_id_for_role,
    load_defaults,
    load_prompt,
)
from labtrust_gym.policy.validate import validate_policy


def test_prompt_registry_validates() -> None:
    """Prompt registry file validates against schema (validate-policy)."""
    root = Path(__file__).resolve().parent.parent
    errors = validate_policy(root)
    prompt_errors = [e for e in errors if "prompt_registry" in e]
    assert not prompt_errors, f"prompt_registry validation failed: {prompt_errors}"


def test_load_prompt_default() -> None:
    """load_prompt() with no args loads default prompt from registry or defaults.yaml."""
    root = Path(__file__).resolve().parent.parent
    templates = load_prompt(repo_root=root)
    assert templates["prompt_id"] == "ops_v2"
    assert templates["prompt_version"] == "2.0.0"
    assert "system_template" in templates
    assert "developer_template" in templates
    assert "user_template" in templates
    assert "{{partner_id}}" in templates["user_template"]


def test_load_defaults() -> None:
    """load_defaults() returns prompt_id and version from defaults.yaml or code default."""
    root = Path(__file__).resolve().parent.parent
    pid, ver = load_defaults(root)
    assert pid == "ops_v2"
    assert ver == "2.0.0"


def test_prompt_fingerprint_stable() -> None:
    """Same inputs => same prompt_fingerprint (stable across runs)."""
    fp1 = compute_prompt_fingerprint(
        "ops_v2",
        "2.0.0",
        partner_id="",
        policy_fingerprint="abc",
        agent_id="ops_0",
        role_id="ops",
        timing_mode="explicit",
    )
    fp2 = compute_prompt_fingerprint(
        "ops_v2",
        "2.0.0",
        partner_id="",
        policy_fingerprint="abc",
        agent_id="ops_0",
        role_id="ops",
        timing_mode="explicit",
    )
    assert fp1 == fp2
    assert len(fp1) == 64
    assert all(c in "0123456789abcdef" for c in fp1)


def test_prompt_fingerprint_changes_with_version() -> None:
    """Changing prompt_version changes prompt_fingerprint."""
    fp_200 = compute_prompt_fingerprint(
        "ops_v2",
        "2.0.0",
        partner_id="",
        policy_fingerprint="",
        agent_id="ops_0",
        role_id="ops",
        timing_mode="explicit",
    )
    fp_201 = compute_prompt_fingerprint(
        "ops_v2",
        "2.0.1",
        partner_id="",
        policy_fingerprint="",
        agent_id="ops_0",
        role_id="ops",
        timing_mode="explicit",
    )
    assert fp_200 != fp_201


def test_prompt_fingerprint_changes_with_partner() -> None:
    """Changing partner_id changes prompt_fingerprint."""
    fp_a = compute_prompt_fingerprint(
        "ops_v2",
        "2.0.0",
        partner_id="",
        policy_fingerprint="",
        agent_id="ops_0",
        role_id="ops",
        timing_mode="explicit",
    )
    fp_b = compute_prompt_fingerprint(
        "ops_v2",
        "2.0.0",
        partner_id="hsl_like",
        policy_fingerprint="",
        agent_id="ops_0",
        role_id="ops",
        timing_mode="explicit",
    )
    assert fp_a != fp_b


def test_llm_decision_includes_prompt_id_version_fingerprint() -> None:
    """LLM_DECISION payload includes prompt_id, prompt_version, prompt_fingerprint, agent_id, role_id."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.llm.agent import (
        DeterministicConstrainedBackend,
        LLMAgentWithShield,
    )

    root = Path(__file__).resolve().parent.parent
    rbac = {
        "roles": [{"role_id": "ops", "allowed_actions": ["NOOP", "TICK"]}],
        "agents": {"ops_0": "ops"},
    }
    agent = LLMAgentWithShield(
        backend=DeterministicConstrainedBackend(seed=42),
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "ops_0"},
        use_action_proposal_schema=True,
    )
    agent.reset(seed=42, partner_id="", timing_mode="explicit")
    obs = {"t_s": 0}
    _, _, meta = agent.act(obs, agent_id="ops_0")
    llm = meta.get("_llm_decision")
    assert llm is not None
    assert llm.get("prompt_id") == DEFAULT_PROMPT_ID
    assert llm.get("prompt_version") == DEFAULT_PROMPT_VERSION
    assert "prompt_fingerprint" in llm
    assert len(llm.get("prompt_fingerprint", "")) == 64
    assert llm.get("agent_id") == "ops_0"
    assert llm.get("role_id") == "ops"


def test_llm_decision_records_agent_id_role_id_prompt_id() -> None:
    """LLM_DECISION records agent_id, role_id, prompt_id (role-aware routing)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.llm.agent import (
        DeterministicConstrainedBackend,
        LLMAgentWithShield,
    )

    root = Path(__file__).resolve().parent.parent
    rbac = {
        "roles": [
            {"role_id": "ROLE_RECEPTION", "allowed_actions": ["NOOP", "TICK"]},
        ],
        "agents": {"ops_0": "ROLE_RECEPTION"},
    }
    agent = LLMAgentWithShield(
        backend=DeterministicConstrainedBackend(seed=43),
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "ops_0"},
        use_action_proposal_schema=True,
    )
    agent.reset(seed=43, partner_id="", timing_mode="explicit")
    obs = {"t_s": 0, "role_id": "ROLE_RECEPTION"}
    _, _, meta = agent.act(obs, agent_id="ops_0")
    llm = meta.get("_llm_decision")
    assert llm is not None
    assert llm.get("agent_id") == "ops_0"
    assert llm.get("role_id") == "ROLE_RECEPTION"
    assert llm.get("prompt_id") == "ops_reception_v2"
    assert get_prompt_id_for_role("ROLE_RECEPTION", root) == "ops_reception_v2"


def test_shift_change_prompt_id_changes_with_role_in_observation() -> None:
    """Shift-change scenario: prompt_id changes after role_id changes (e.g. after UPDATE_ROSTER)."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.baselines.llm.agent import (
        DeterministicConstrainedBackend,
        LLMAgentWithShield,
    )

    root = Path(__file__).resolve().parent.parent
    rbac = {
        "roles": [
            {"role_id": "ROLE_RECEPTION", "allowed_actions": ["NOOP", "TICK"]},
            {"role_id": "ROLE_ANALYTICS", "allowed_actions": ["NOOP", "TICK"]},
        ],
        "agents": {"ops_0": "ROLE_RECEPTION"},
    }
    agent = LLMAgentWithShield(
        backend=DeterministicConstrainedBackend(seed=44),
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "ops_0"},
        use_action_proposal_schema=True,
    )
    agent.reset(seed=44, partner_id="", timing_mode="explicit")

    obs_reception = {"t_s": 0, "role_id": "ROLE_RECEPTION"}
    _, _, meta1 = agent.act(obs_reception, agent_id="ops_0")
    llm1 = meta1.get("_llm_decision")
    assert llm1 is not None
    assert llm1.get("prompt_id") == "ops_reception_v2"
    assert llm1.get("role_id") == "ROLE_RECEPTION"

    obs_analytics = {"t_s": 10, "role_id": "ROLE_ANALYTICS"}
    _, _, meta2 = agent.act(obs_analytics, agent_id="ops_0")
    llm2 = meta2.get("_llm_decision")
    assert llm2 is not None
    assert llm2.get("prompt_id") == "ops_analytics_v2"
    assert llm2.get("role_id") == "ROLE_ANALYTICS"

    assert llm1.get("prompt_id") != llm2.get("prompt_id")
