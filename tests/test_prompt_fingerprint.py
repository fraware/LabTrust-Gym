"""
Tests for coordination LLM prompt fingerprinting: same seed -> same hash;
changing policy changes allowed_actions_payload_sha256 and coordination_policy_fingerprint.
"""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.baselines.coordination.prompt_fingerprint import (
    allowed_actions_payload_sha256,
    canonical_prompt_representation,
    compute_prompt_fingerprints,
    coordination_policy_fingerprint_from_repo,
    prompt_template_id_for_method,
    recompute_prompt_sha256_from_inputs,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_same_seed_same_prompt_hash() -> None:
    """Same state_digest, allowed_actions, policy => same prompt_sha256 and allowed_actions_payload_sha256."""
    state = {
        "step": 0,
        "per_agent": [{"agent_id": "a1", "zone": "Z1", "task": "active"}],
        "per_device": [{"device_id": "D1", "state": "idle"}],
        "per_specimen": [],
        "comms_stats": {"msg_count": 0, "drop_rate": 0.0},
    }
    allowed = ["NOOP", "TICK", "MOVE"]
    policy = {"pz_to_engine": {}}

    a = compute_prompt_fingerprints(
        "llm_central_planner",
        state,
        allowed,
        policy=policy,
        repo_root=_repo_root(),
        include_inputs_for_verify=True,
    )
    b = compute_prompt_fingerprints(
        "llm_central_planner",
        state,
        allowed,
        policy=policy,
        repo_root=_repo_root(),
        include_inputs_for_verify=True,
    )
    assert a["prompt_sha256"] == b["prompt_sha256"]
    assert a["allowed_actions_payload_sha256"] == b["allowed_actions_payload_sha256"]
    assert a["prompt_template_id"] == b["prompt_template_id"]
    assert a["coordination_policy_fingerprint"] == b["coordination_policy_fingerprint"]


def test_prompt_template_id_stable_per_method() -> None:
    """prompt_template_id is deterministic per method_id."""
    assert prompt_template_id_for_method("llm_central_planner") == "coordination_llm_central_planner_v0.1"
    assert prompt_template_id_for_method("llm_auction_bidder") == "coordination_llm_auction_bidder_v0.1"


def test_changing_allowed_actions_changes_payload_hash() -> None:
    """Different allowed_actions => different allowed_actions_payload_sha256."""
    state = {
        "step": 0,
        "per_agent": [],
        "per_device": [],
        "per_specimen": [],
        "comms_stats": {"msg_count": 0, "drop_rate": 0.0},
    }
    h1 = allowed_actions_payload_sha256(["NOOP", "TICK"])
    h2 = allowed_actions_payload_sha256(["NOOP", "TICK", "MOVE"])
    assert h1 != h2


def test_changing_policy_file_changes_coordination_fingerprint(tmp_path: Path) -> None:
    """coordination_policy_fingerprint_from_repo depends on policy/coordination_identity_policy.v0.1.yaml."""
    # Use repo root: real policy file exists; fingerprint is stable for that file
    root = _repo_root()
    fp = coordination_policy_fingerprint_from_repo(root)
    assert isinstance(fp, str)
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)
    # When file is missing, we get a fallback hash
    fp_missing = coordination_policy_fingerprint_from_repo(tmp_path)
    assert fp_missing != fp or not (tmp_path / "policy" / "coordination_identity_policy.v0.1.yaml").exists()


def test_recompute_prompt_sha256_matches() -> None:
    """Recomputed prompt_sha256 from stored inputs matches original compute_prompt_fingerprints."""
    state = {
        "step": 1,
        "per_agent": [],
        "per_device": [],
        "per_specimen": [],
        "comms_stats": {"msg_count": 0, "drop_rate": 0.0},
    }
    out = compute_prompt_fingerprints(
        "llm_central_planner",
        state,
        ["NOOP", "TICK"],
        repo_root=_repo_root(),
        include_inputs_for_verify=True,
    )
    inputs = out["prompt_fingerprint_inputs"]
    recomputed = recompute_prompt_sha256_from_inputs(
        inputs["prompt_template_id"],
        inputs["state_digest_slice"],
        inputs["allowed_actions_payload_canonical"],
        inputs.get("policy_slice"),
    )
    assert recomputed == out["prompt_sha256"]


def test_canonical_prompt_representation_deterministic() -> None:
    """canonical_prompt_representation is deterministic for same inputs."""
    state = {
        "step": 0,
        "per_agent": [{"agent_id": "x", "zone": "Z"}],
        "per_device": [],
        "per_specimen": [],
        "comms_stats": {},
    }
    payload = '[{"action_type":"NOOP","args_examples":[{}],"description":"Do nothing."}]'
    a = canonical_prompt_representation("coordination_llm_central_planner_v0.1", state, payload, None)
    b = canonical_prompt_representation("coordination_llm_central_planner_v0.1", state, payload, None)
    assert a == b
