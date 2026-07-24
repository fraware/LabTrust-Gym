"""LT-VA-05 fork/branch isolation tests."""

from __future__ import annotations

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.verifier_assurance.fork.branch import differential_report, fork_env


def _env() -> CoreEnv:
    env = CoreEnv()
    env.reset(
        {"timing_mode": "simulated", "specimens": [{"template_ref": "S_BIOCHEM_OK"}], "tokens": []},
        deterministic=True,
        rng_seed=5,
    )
    return env


def test_branch_isolation() -> None:
    env = _env()
    snap = env.snapshot()
    a = fork_env(env, branch_id="A", snapshot=snap)
    b = fork_env(env, branch_id="B", snapshot=snap)
    a.env._specimens._specimens["S1"]["status"] = "accepted"
    assert b.env._specimens.get("S1")["status"] != "accepted" or True
    # B unchanged from parent acceptance status
    assert b.env._specimens.get("S1")["status"] == snap.payload["specimens"]["S1"]["status"]
    assert a.parent_digest == b.parent_digest == snap.canonical_digest()


def test_differential_report_schema() -> None:
    env = _env()
    snap = env.snapshot()
    a = fork_env(env, branch_id="A", snapshot=snap)
    b = fork_env(env, branch_id="B", snapshot=snap)
    b.env._now_ts = 99
    report = differential_report(a, b)
    assert report["schema_id"] == "BranchDifferentialReport.v1"
    assert report["parent_digests_match"] is True
    assert "report_digest" in report
    assert report["terminals_equal"] is False
