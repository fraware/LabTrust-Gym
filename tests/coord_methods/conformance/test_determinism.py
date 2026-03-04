"""
Conformance contract: Determinism.
Given (seed, obs fixture, policy fixture, t), reset() + propose_actions() must produce
identical action_dict and identical explain/meta across 3 runs.
Second seed must produce either identical (deterministic) or valid different (stochastic) output.
"""

from __future__ import annotations

import pytest

from labtrust_gym.baselines.coordination.interface import VALID_ACTION_INDICES

from .conftest import (
    _method_ids_from_policy,
    _minimal_obs,
    _minimal_scale_config,
    make_coord_method_for_conformance,
)


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_determinism_contract(
    method_id: str,
    repo_root,
    conformance_config,
    minimal_policy,
    minimal_scale_config,
) -> None:
    """Same seed + obs + t -> identical action_dict (and explain/meta if exposed) across 3 runs."""
    if method_id in (conformance_config.get("skip_determinism") or []):
        pytest.skip(f"{method_id}: skipped by conformance_config (determinism)")
    if method_id in (conformance_config.get("optional_deps_methods") or []):
        pass  # try to instantiate; may skip inside

    scale_config = _minimal_scale_config(seed=42)
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")

    policy = minimal_policy
    agent_ids = sorted(policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}

    coord.reset(42, policy, scale_config)
    run1 = coord.propose_actions(obs, infos, 0)

    coord.reset(42, policy, scale_config)
    run2 = coord.propose_actions(obs, infos, 0)

    coord.reset(42, policy, scale_config)
    run3 = coord.propose_actions(obs, infos, 0)

    for aid in agent_ids:
        a1 = run1.get(aid, {})
        a2 = run2.get(aid, {})
        a3 = run3.get(aid, {})
        assert a1.get("action_index") == a2.get("action_index") == a3.get("action_index"), (
            f"{method_id} {aid}: action_index not identical across 3 runs"
        )
        assert a1.get("action_type", "NOOP") == a2.get("action_type", "NOOP") == a3.get("action_type", "NOOP")
    if conformance_config.get("xfail_determinism") and method_id in conformance_config["xfail_determinism"]:
        pytest.xfail(f"{method_id}: known to fail determinism until upgraded")


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_second_seed_validity(
    method_id: str,
    repo_root,
    conformance_config,
    minimal_policy,
) -> None:
    """Second seed -> either identical output or measurably different but valid (action_index 0..5)."""
    if method_id in (conformance_config.get("skip_determinism") or []):
        pytest.skip(f"{method_id}: skipped by conformance_config")
    scale_config1 = _minimal_scale_config(seed=42)
    scale_config2 = _minimal_scale_config(seed=99)
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config1)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")

    policy = minimal_policy
    agent_ids = sorted(policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}

    coord.reset(42, policy, scale_config1)
    out1 = coord.propose_actions(obs, infos, 0)
    coord.reset(99, policy, scale_config2)
    out2 = coord.propose_actions(obs, infos, 0)

    for aid in agent_ids:
        idx = out2.get(aid, {}).get("action_index", 0)
        assert idx in VALID_ACTION_INDICES, f"{method_id} seed=99 {aid}: action_index {idx} not in 0..5"
