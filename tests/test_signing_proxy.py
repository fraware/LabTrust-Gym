"""
Tests for signing proxy: select_key, sign_event_payload, key lifecycle, fixture loading.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from labtrust_gym.baselines.llm.signing_proxy import (
    ensure_run_ephemeral_key,
    generate_ephemeral_keypair,
    load_private_key_from_fixture,
    select_key,
    sign_event_payload,
)
from labtrust_gym.engine.signatures import (
    build_signing_payload,
    canonical_payload_bytes,
    verify_signature,
)

FIXTURES_KEYS = Path(__file__).resolve().parent / "fixtures" / "keys"


def test_select_key_returns_first_active_key_for_agent_role() -> None:
    registry = {
        "version": "0.1",
        "keys": [
            {
                "key_id": "ed25519:key_reception",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
                "status": "ACTIVE",
                "not_before_ts_s": None,
                "not_after_ts_s": None,
            },
        ],
    }
    key_id = select_key("A_RECEPTION", "ROLE_RECEPTION", 0, registry)
    assert key_id == "ed25519:key_reception"


def test_select_key_skips_revoked_keys() -> None:
    registry = {
        "version": "0.1",
        "keys": [
            {
                "key_id": "ed25519:key_revoked",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_INSIDER_0",
                "role_id": "ROLE_INSIDER",
                "status": "REVOKED",
                "not_before_ts_s": None,
                "not_after_ts_s": None,
            },
        ],
    }
    key_id = select_key("A_INSIDER_0", "ROLE_INSIDER", 0, registry)
    assert key_id is None


def test_select_key_skips_expired_keys() -> None:
    registry = {
        "version": "0.1",
        "keys": [
            {
                "key_id": "ed25519:key_expired",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
                "status": "ACTIVE",
                "not_before_ts_s": 0,
                "not_after_ts_s": 100,
            },
        ],
    }
    key_id = select_key("A_RECEPTION", "ROLE_RECEPTION", 200, registry)
    assert key_id is None


def test_select_key_skips_not_yet_valid_keys() -> None:
    registry = {
        "version": "0.1",
        "keys": [
            {
                "key_id": "ed25519:key_future",
                "public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiNa8CGmj3B1Eao=",
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
                "status": "ACTIVE",
                "not_before_ts_s": 1000,
                "not_after_ts_s": None,
            },
        ],
    }
    key_id = select_key("A_RECEPTION", "ROLE_RECEPTION", 0, registry)
    assert key_id is None


def test_sign_event_payload_produces_verifiable_signature() -> None:
    priv, pub_b64 = generate_ephemeral_keypair()
    action = {
        "action_type": "MOVE",
        "args": {"from_zone": "Z_A", "to_zone": "Z_B"},
        "token_refs": [],
    }
    event_id = "pz_ops_0_1"
    t_s = 10
    agent_id = "A_RECEPTION"
    prev_hash = "abc"
    partner_id = "P1"
    policy_fingerprint = "fp1"
    sig = sign_event_payload(action, event_id, t_s, agent_id, prev_hash, partner_id, policy_fingerprint, priv)
    assert sig is not None
    payload = build_signing_payload(
        event_id,
        t_s,
        agent_id,
        "MOVE",
        dict(action["args"]),
        list(action.get("token_refs") or []),
        partner_id,
        policy_fingerprint,
        prev_hash,
    )
    payload_bytes = canonical_payload_bytes(payload)
    assert verify_signature(payload_bytes, sig, pub_b64) is True


def test_load_private_key_from_fixture() -> None:
    priv_path = FIXTURES_KEYS / "key_reception_private.b64"
    if not priv_path.exists():
        pytest.skip("fixture keys not present")
    priv = load_private_key_from_fixture(priv_path)
    assert priv is not None
    assert len(priv) == 32


def test_generate_ephemeral_keypair() -> None:
    priv, pub_b64 = generate_ephemeral_keypair()
    assert len(priv) == 32
    raw = base64.b64decode(pub_b64, validate=True)
    assert len(raw) == 32


def test_llm_agent_strict_signatures_attach_signed_by_proxy() -> None:
    """Strict_signatures + key_registry: mutating action gets key_id/sig; LLM_DECISION has signed_by_proxy."""
    priv, pub_b64 = generate_ephemeral_keypair()
    key_id = "ed25519:key_test_ops"
    key_registry = {
        "version": "0.1",
        "keys": [
            {
                "key_id": key_id,
                "public_key": pub_b64,
                "agent_id": "A_RECEPTION",
                "role_id": "ROLE_RECEPTION",
                "status": "ACTIVE",
                "not_before_ts_s": None,
                "not_after_ts_s": None,
            },
        ],
    }

    def get_private_key(kid: str):
        if kid == key_id:
            return priv
        return None

    from labtrust_gym.baselines.llm.agent import (
        DeterministicConstrainedBackend,
        LLMAgentWithShield,
    )
    from labtrust_gym.engine.rbac import load_rbac_policy

    repo_root = Path(__file__).resolve().parent.parent
    rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
    rbac_policy = load_rbac_policy(rbac_path)
    backend = DeterministicConstrainedBackend(seed=42, default_action_type="TICK", first_action_type="TICK")
    pz_to_engine = {"ops_0": "A_RECEPTION"}
    agent = LLMAgentWithShield(
        backend=backend,
        rbac_policy=rbac_policy,
        pz_to_engine=pz_to_engine,
        strict_signatures=True,
        key_registry=key_registry,
        get_private_key=get_private_key,
    )
    agent.reset(0, policy_summary={"policy_fingerprint": "fp"}, partner_id="P1")
    observation = {
        "t_s": 10,
        "prev_hash": "abc",
        "next_event_id": "pz_ops_0_1",
        "next_t_s": 10,
        "zone_id": "Z_ANALYZER_HALL_A",
        "queue_by_device": [],
    }
    action_idx, action_info, meta = agent.act(observation, agent_id="ops_0")
    assert action_info.get("key_id") is not None
    assert action_info.get("signature") is not None
    llm_decision = meta.get("_llm_decision") or {}
    assert llm_decision.get("signed_by_proxy") is True
    assert llm_decision.get("key_id_used") == key_id


def test_ensure_run_ephemeral_key_returns_merged_registry_and_get_private_key(
    tmp_path: Path,
) -> None:
    base = {"version": "0.1", "keys": []}
    merged, get_pk = ensure_run_ephemeral_key(tmp_path, "A_OPS_0", "ROLE_ANALYTICS", base)
    assert "keys" in merged
    assert len(merged["keys"]) >= 1
    run_key = next((k for k in merged["keys"] if k.get("agent_id") == "A_OPS_0"), None)
    assert run_key is not None
    key_id = run_key["key_id"]
    priv = get_pk(key_id)
    assert priv is not None and len(priv) == 32
    assert get_pk("other_key") is None
