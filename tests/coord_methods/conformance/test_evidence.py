"""
Conformance contract: Evidence (METHOD_TRACE.jsonl).
Each method must write METHOD_TRACE.jsonl (one JSON per decision stage); test asserts
file exists, valid JSONL, and same seed -> same trace content/hash.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.baselines.coordination.trace import (
    append_trace_event,
    build_method_trace_event,
    trace_event_hash,
    trace_from_contract_record,
)

from .conftest import (
    _method_ids_from_policy,
    _minimal_obs,
    _minimal_scale_config,
    make_coord_method_for_conformance,
)


@pytest.mark.parametrize("method_id", _method_ids_from_policy())
def test_evidence_contract(
    method_id: str,
    repo_root: Path,
    conformance_config: dict,
    minimal_policy: dict,
    minimal_scale_config: dict,
    tmp_path: Path,
) -> None:
    """When method emits trace (or runner writes minimal), file exists, valid JSONL."""
    pass_evidence = conformance_config.get("pass_evidence") or []
    if method_id not in pass_evidence:
        pytest.skip(
            f"{method_id}: not in pass_evidence; add when method emits trace"
        )

    scale_config = _minimal_scale_config()
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")

    agent_ids = sorted(
        minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"]
    )
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}
    trace_path = tmp_path / "METHOD_TRACE.jsonl"

    coord.reset(42, minimal_policy, scale_config)
    actions_dict = coord.propose_actions(obs, infos, 0)

    # Runner-style: write minimal trace if method does not write to path
    event = trace_from_contract_record(method_id, 0, actions_dict)
    append_trace_event(trace_path, event)

    assert trace_path.exists()
    lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    for line in lines:
        parsed = json.loads(line)
        assert "method_id" in parsed and parsed["method_id"] == method_id
        assert "t_step" in parsed and "stage" in parsed

    # Stability: same seed again -> same trace content
    trace_path2 = tmp_path / "METHOD_TRACE2.jsonl"
    coord.reset(42, minimal_policy, scale_config)
    actions_dict2 = coord.propose_actions(obs, infos, 0)
    event2 = trace_from_contract_record(method_id, 0, actions_dict2)
    append_trace_event(trace_path2, event2)
    assert trace_event_hash(event) == trace_event_hash(event2)


def test_composed_kernel_writes_trace_when_trace_path_set(
    repo_root: Path,
    minimal_policy: dict,
    tmp_path: Path,
) -> None:
    """Composed kernel (e.g. kernel_whca) writes METHOD_TRACE when scale_config.trace_path set."""
    from .conftest import (
        _minimal_obs,
        _minimal_scale_config,
        make_coord_method_for_conformance,
    )

    method_id = "kernel_whca"
    scale_config = _minimal_scale_config()
    scale_config["trace_path"] = str(tmp_path / "METHOD_TRACE.jsonl")
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip("kernel_whca not available")

    agent_ids = sorted(
        minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"]
    )
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}

    coord.reset(42, minimal_policy, scale_config)
    coord.propose_actions(obs, infos, 0)

    trace_path = Path(scale_config["trace_path"])
    assert trace_path.exists()
    lines = trace_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    assert rec.get("method_id") == method_id and rec.get("t_step") == 0


def test_trace_event_build_and_hash_stable() -> None:
    """Unit: build_method_trace_event and trace_event_hash are deterministic."""
    e1 = build_method_trace_event(
        "kernel_whca", 0, "route", duration_ms=1.5, outcome="ok"
    )
    e2 = build_method_trace_event(
        "kernel_whca", 0, "route", duration_ms=1.5, outcome="ok"
    )
    assert trace_event_hash(e1) == trace_event_hash(e2)
    e3 = build_method_trace_event(
        "kernel_whca", 0, "route", duration_ms=1.6, outcome="ok"
    )
    assert trace_event_hash(e1) != trace_event_hash(e3)


def test_evidence_diff_stability_same_seed_same_trace_hash(
    repo_root: Path,
    conformance_config: dict,
    minimal_policy: dict,
    tmp_path: Path,
) -> None:
    """
    Evidence diff stability: for methods in pass_evidence, same seed and policy
    must yield same METHOD_TRACE event hash across two runs (determinism for evidence).
    """
    from labtrust_gym.baselines.coordination.trace import (
        append_trace_event,
        trace_event_hash,
        trace_from_contract_record,
    )
    from .conftest import (
        _minimal_obs,
        _minimal_scale_config,
        make_coord_method_for_conformance,
    )

    pass_evidence = conformance_config.get("pass_evidence") or []
    if not pass_evidence:
        pytest.skip("no pass_evidence methods")
    method_id = pass_evidence[0]
    scale_config = _minimal_scale_config()
    coord = make_coord_method_for_conformance(method_id, repo_root, scale_config)
    if coord is None:
        pytest.skip(f"{method_id}: optional deps missing")
    agent_ids = sorted(minimal_policy.get("pz_to_engine") or ["worker_0", "worker_1", "worker_2"])
    obs = _minimal_obs(agent_ids, 0)
    infos: dict = {}
    coord.reset(42, minimal_policy, scale_config)
    actions1 = coord.propose_actions(obs, infos, 0)
    event1 = trace_from_contract_record(method_id, 0, actions1)
    coord.reset(42, minimal_policy, scale_config)
    actions2 = coord.propose_actions(obs, infos, 0)
    event2 = trace_from_contract_record(method_id, 0, actions2)
    assert trace_event_hash(event1) == trace_event_hash(event2), (
        "Same seed and policy must yield same trace hash (evidence diff stability)"
    )
