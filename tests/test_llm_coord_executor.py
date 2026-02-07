"""
Tests for LLM coordination proposal executor: execute_proposal, repair loop,
deterministic hashes, and attempt logging.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.llm_executor import (
    ExecutionReport,
    _proposal_hash,
    _repair_request_hash,
    _shield_outcome_hash,
    build_repair_request,
    execute_proposal,
    execute_proposal_shield_only,
    get_actions_from_proposal,
    run_proposal_with_repair,
)
from labtrust_gym.baselines.llm.shield import apply_shield
from labtrust_gym.baselines.llm.shield import build_policy_summary


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _minimal_rbac_only_noop_tick() -> dict:
    """RBAC that allows only NOOP and TICK (so QUEUE_RUN is blocked)."""
    return {
        "version": "0.1",
        "roles": {"ROLE_RUNNER": {"allowed_actions": ["NOOP", "TICK"]}},
        "agents": {
            "ops_0": "ROLE_RUNNER",
            "runner_0": "ROLE_RUNNER",
        },
        "action_constraints": {},
    }


def _minimal_proposal_dict(
    agent_id: str = "runner_0", action_type: str = "NOOP"
) -> dict:
    """Minimal valid proposal for one agent."""
    return {
        "proposal_id": "test-001",
        "step_id": 0,
        "method_id": "llm_constrained",
        "horizon_steps": 1,
        "per_agent": [
            {
                "agent_id": agent_id,
                "action_type": action_type,
                "args": (
                    {}
                    if action_type in ("NOOP", "TICK")
                    else {
                        "device_id": "DEV_CHEM_A_01",
                        "work_id": "w1",
                        "priority_class": "ROUTINE",
                    }
                ),
                "reason_code": "LLM_INVALID_SCHEMA",
            },
        ],
        "comms": [],
        "meta": {"backend_id": "test", "latency_ms": 0},
    }


@pytest.fixture
def pz_env():
    """Minimal PZ env (1 runner) for executor tests."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    env = LabTrustParallelEnv(num_runners=1)
    env.reset(seed=42)
    yield env
    env.close()


def test_proposal_with_invalid_action_blocked_no_state_mutation(pz_env) -> None:
    """One disallowed action is blocked; shield substitutes NOOP."""
    rbac = _minimal_rbac_only_noop_tick()
    policy_summary = build_policy_summary(allowed_actions=["NOOP", "TICK"])
    proposal = _minimal_proposal_dict(agent_id="runner_0", action_type="QUEUE_RUN")

    report = execute_proposal(
        pz_env,
        proposal,
        apply_shield,
        rbac,
        policy_summary,
        strict=True,
    )

    assert isinstance(report, ExecutionReport)
    assert len(report.blocked_actions) >= 1
    runner_blocked = [
        b for b in report.blocked_actions
        if b.get("blocked_reason_code") and b.get("agent_id") == "runner_0"
    ]
    assert len(runner_blocked) >= 1
    assert report.proposal_hash
    assert report.shield_outcome_hash
    assert report.comms_delivered_count == 0
    assert report.comms_dropped_count == 0


def test_repair_attempt_logs_and_stops_at_cap() -> None:
    """Repair loop logs each attempt and stops at max_repairs."""
    attempts_logged: list[dict] = []

    def propose(obs, infos, t, repair_request=None):
        if repair_request is not None and len(attempts_logged) >= 1:
            return _minimal_proposal_dict("runner_0", "TICK")
        return _minimal_proposal_dict("runner_0", "QUEUE_RUN")

    def validate(proposal):
        at = (proposal.get("per_agent") or [{}])[0].get("action_type")
        if at == "QUEUE_RUN":
            return False, ["action_type not in allowed_actions"]
        return True, []

    class FakeEnv:
        agents = ["runner_0"]

        def step(self, actions, action_infos=None):
            res = [{"status": "OK"}]
            infos = {
                "runner_0": {"_benchmark_step_results": res},
            }
            return (
                {},
                {a: 0.0 for a in self.agents},
                {a: False for a in self.agents},
                {a: False for a in self.agents},
                infos,
            )

    rbac = _minimal_rbac_only_noop_tick()
    policy_summary = build_policy_summary(allowed_actions=["NOOP", "TICK"])

    def log_attempt(record):
        attempts_logged.append(dict(record))

    final_proposal, report, attempt_count = run_proposal_with_repair(
        propose,
        FakeEnv(),
        apply_shield,
        rbac,
        policy_summary,
        obs={},
        infos={},
        t=0,
        validate_fn=validate,
        max_repairs=1,
        log_attempt_fn=log_attempt,
    )

    assert attempt_count >= 1
    assert len(attempts_logged) >= 1
    for r in attempts_logged:
        assert r.get("log_type") == "LLM_COORD_PROPOSAL_ATTEMPT"
    assert all("attempt_index" in r for r in attempts_logged)
    assert attempt_count <= 2


def test_outcomes_deterministic_same_inputs(pz_env) -> None:
    """Same proposal and env seed yield same proposal_hash and shield_outcome_hash."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    rbac = _minimal_rbac_only_noop_tick()
    policy_summary = build_policy_summary(allowed_actions=["NOOP", "TICK"])
    proposal = _minimal_proposal_dict("runner_0", "TICK")

    def run_once():
        env = LabTrustParallelEnv(num_runners=1)
        env.reset(seed=99)
        report = execute_proposal(
            env,
            proposal,
            apply_shield,
            rbac,
            policy_summary,
            strict=True,
        )
        env.close()
        return report.proposal_hash, report.shield_outcome_hash

    h1, s1 = run_once()
    h2, s2 = run_once()
    assert h1 == h2
    assert s1 == s2


def test_proposal_hash_repair_request_hash_deterministic() -> None:
    """_proposal_hash and _repair_request_hash are deterministic for same input."""
    proposal = _minimal_proposal_dict()
    assert _proposal_hash(proposal) == _proposal_hash(proposal)
    req = build_repair_request(
        blocked_reason_codes=["RBAC_ACTION_DENY"],
        failed_validation_fields=[],
        state_digest={"step": 0},
    )
    assert _repair_request_hash(req) == _repair_request_hash(req)


def test_shield_outcome_hash_deterministic() -> None:
    """_shield_outcome_hash is deterministic for same executed and blocked lists."""
    executed = [{"agent_id": "a", "action_type": "NOOP"}]
    blocked = [{"agent_id": "b", "blocked_reason_code": "RC"}]
    assert _shield_outcome_hash(executed, blocked) == _shield_outcome_hash(
        executed, blocked
    )


def test_build_repair_request() -> None:
    """build_repair_request returns payload with expected keys."""
    req = build_repair_request(
        blocked_reason_codes=["RBAC_ACTION_DENY"],
        failed_validation_fields=["per_agent[0].action_type"],
        state_digest={"step": 1, "attempt": 1},
    )
    assert "blocked_reason_codes" in req
    assert "failed_validation_fields" in req
    assert "state_digest" in req
    assert req["blocked_reason_codes"] == ["RBAC_ACTION_DENY"]
    assert "per_agent" in str(req["failed_validation_fields"])


def test_execute_proposal_shield_only_no_env_step(pz_env) -> None:
    """execute_proposal_shield_only returns ExecutionReport without calling env.step."""
    step_calls: list[tuple] = []

    class EnvWithStepSpy:
        def __init__(self, real_env):
            self._env = real_env
            self.agents = getattr(real_env, "agents", real_env.possible_agents)

        def step(self, actions, action_infos=None):
            step_calls.append((actions, action_infos))
            return self._env.step(actions, action_infos=action_infos)

    rbac = _minimal_rbac_only_noop_tick()
    policy_summary = build_policy_summary(allowed_actions=["NOOP", "TICK"])
    proposal = _minimal_proposal_dict("runner_0", "TICK")
    env_spy = EnvWithStepSpy(pz_env)

    report = execute_proposal_shield_only(
        env_spy,
        proposal,
        apply_shield,
        rbac,
        policy_summary,
    )

    assert len(step_calls) == 0
    assert isinstance(report, ExecutionReport)
    assert report.proposal_hash
    assert report.shield_outcome_hash
    assert report.step_results == []
    assert report.invariant_violations_delta == []


def test_get_actions_from_proposal(pz_env) -> None:
    """get_actions_from_proposal returns (actions, action_infos) for env.step."""
    rbac = _minimal_rbac_only_noop_tick()
    policy_summary = build_policy_summary(allowed_actions=["NOOP", "TICK"])
    proposal = _minimal_proposal_dict("runner_0", "TICK")

    actions, action_infos = get_actions_from_proposal(
        pz_env,
        proposal,
        apply_shield,
        rbac,
        policy_summary,
    )

    agents = list(getattr(pz_env, "agents", pz_env.possible_agents))
    assert set(actions.keys()) == set(agents)
    assert set(action_infos.keys()) <= set(agents)
    for aid in agents:
        assert isinstance(actions[aid], int)
        assert 0 <= actions[aid]


def test_run_proposal_with_repair_shield_only_no_env_step() -> None:
    """run_proposal_with_repair(execute_fn=execute_proposal_shield_only) does not call env.step."""
    step_calls: list[tuple] = []

    def propose(obs, infos, t, repair_request=None):
        return _minimal_proposal_dict("runner_0", "TICK")

    def validate(proposal):
        return True, []

    class FakeEnv:
        agents = ["runner_0"]

        def step(self, actions, action_infos=None):
            step_calls.append((actions, action_infos))
            return (
                {},
                {a: 0.0 for a in self.agents},
                {a: False for a in self.agents},
                {a: False for a in self.agents},
                {a: {"_benchmark_step_results": [{"status": "OK"}]} for a in self.agents},
            )

    rbac = _minimal_rbac_only_noop_tick()
    policy_summary = build_policy_summary(allowed_actions=["NOOP", "TICK"])
    env = FakeEnv()

    final_proposal, report, attempt_count = run_proposal_with_repair(
        propose,
        env,
        apply_shield,
        rbac,
        policy_summary,
        obs={},
        infos={},
        t=0,
        validate_fn=validate,
        max_repairs=1,
        execute_fn=execute_proposal_shield_only,
    )

    assert len(step_calls) == 0
    assert final_proposal is not None
    assert report is not None
    assert report.proposal_hash
    assert report.shield_outcome_hash
    assert attempt_count >= 1
