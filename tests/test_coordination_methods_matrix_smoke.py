"""
Parametrized coordination test harness: methods x tasks x scale (S only).

Validates every coordination method the same way:
- Results schema valid
- No crashes
- Required coordination metrics present
- Comm metrics non-negative
- Security metrics present for TaskH
- Determinism (rerun same seed -> identical metrics) for deterministic methods

Gate:
- Default: run only a small subset of baseline method_ids (fast CI).
- LABTRUST_COORDINATION_SMOKE=1: run full matrix (all method_ids, both tasks).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.benchmarks.summarize import validate_results_v02
from labtrust_gym.policy.coordination import load_coordination_methods


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _coordination_smoke_full() -> bool:
    """True when LABTRUST_COORDINATION_SMOKE=1 (run full coordination matrix)."""
    v = os.environ.get("LABTRUST_COORDINATION_SMOKE", "")
    return str(v).strip() == "1"


def _all_method_ids() -> list[str]:
    """All method_ids from coordination_methods.v0.1.yaml."""
    path = _repo_root() / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
    if not path.exists():
        return []
    registry = load_coordination_methods(path)
    return sorted(registry.keys())


# Small subset for default (no env var): existing baseline methods for speed.
BASELINE_METHOD_IDS = [
    "centralized_planner",
    "kernel_centralized_edf",
    "kernel_auction_whca_shielded",
    "group_evolving_experience_sharing",
]

# Methods that require special setup (e.g. llm_agent) or optional deps; skip in matrix.
SKIP_METHOD_IDS = frozenset({"llm_constrained", "marl_ppo"})


def _method_ids_for_matrix() -> list[str]:
    all_ids = _all_method_ids()
    if _coordination_smoke_full():
        return [m for m in all_ids if m not in SKIP_METHOD_IDS]
    subset = [m for m in BASELINE_METHOD_IDS if m in all_ids]
    return subset if subset else BASELINE_METHOD_IDS


# TaskG (nominal) + TaskH (one injection). Scale S only = small_smoke.
TASK_CONFIGS = [
    ("coord_scale", None),
    ("coord_risk", "INJ-COMMS-POISON-001"),
]

SCALE_ID = "small_smoke"

# Methods considered deterministic for determinism assertion (same seed -> same metrics).
# Exclude methods that may be non-deterministic even with pipeline_mode=deterministic.
DETERMINISTIC_METHOD_IDS = frozenset(
    {
        "centralized_planner",
        "kernel_centralized_edf",
        "kernel_whca",
        "kernel_scheduler_or",
        "kernel_scheduler_or_whca",
        "kernel_auction_edf",
        "kernel_auction_whca",
        "kernel_auction_whca_shielded",
        "hierarchical_hub_rr",
        "hierarchical_hub_local",
        "market_auction",
        "gossip_consensus",
        "swarm_reactive",
        "ripple_effect",
        "group_evolving_experience_sharing",
        "group_evolving_study",
        "llm_central_planner",
        "llm_hierarchical_allocator",
        "llm_auction_bidder",
        "llm_gossip_summarizer",
        "llm_local_decider_signed_bus",
        "llm_repair_over_kernel_whca",
        "llm_detector_throttle_advisor",
    }
)


@pytest.fixture(scope="module")
def _scale_config_s():
    """Scale S (small_smoke) for speed."""
    root = _repo_root()
    try:
        return load_scale_config_by_id(root, SCALE_ID)
    except (KeyError, FileNotFoundError) as e:
        pytest.skip(f"Scale {SCALE_ID} not available: {e}")


@pytest.mark.parametrize("method_id", _method_ids_for_matrix())
@pytest.mark.parametrize("task_injection", TASK_CONFIGS, ids=["CoordinationScale", "CoordinationRisk_INJ"])
def test_coordination_matrix_smoke(
    tmp_path: Path,
    method_id: str,
    task_injection: tuple[str, str | None],
    _scale_config_s,
) -> None:
    """
    Single matrix cell: run task with coord method on scale S.
    Assert: schema valid, no crash, coordination metrics present,
    comm metrics non-negative, security metrics for CoordinationRisk, and determinism when applicable.
    """
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    task_name, injection_id = task_injection
    repo_root = _repo_root()
    scale_config = _scale_config_s
    out_path = tmp_path / f"results_{method_id}_{task_name}.json"

    try:
        results = run_benchmark(
            task_name=task_name,
            num_episodes=1,
            base_seed=42,
            out_path=out_path,
            repo_root=repo_root,
            coord_method=method_id,
            injection_id=injection_id,
            scale_config_override=scale_config,
            pipeline_mode="deterministic",
        )
    except (ValueError, ImportError, NotImplementedError, RuntimeError) as e:
        if method_id in SKIP_METHOD_IDS or "marl_ppo" in method_id or "llm_constrained" in str(e).lower():
            pytest.skip(f"{method_id} requires special setup or deps: {e}")
        raise

    assert results is not None, "run_benchmark must return results"
    errors = validate_results_v02(results)
    assert not errors, f"Results schema invalid: {errors}"

    episodes = results.get("episodes") or []
    assert len(episodes) >= 1, "At least one episode"
    metrics = episodes[0].get("metrics") or {}

    coord = metrics.get("coordination") or {}
    assert coord, f"Coordination metrics must be present for coord_method={method_id}"

    comm = coord.get("comm") or {}
    for key in ("msg_count", "invalid_sig_count", "replay_drop_count"):
        if key in comm and comm[key] is not None:
            assert comm[key] >= 0, f"comm.{key} must be non-negative, got {comm[key]}"

    if task_name == "coord_risk":
        sec = metrics.get("sec") or {}
        assert sec, "TaskH must produce security metrics (sec)"
        assert (
            "injection_id" in sec
            or "attack_success_rate" in sec
            or "detection_latency_steps" in sec
            or "containment_time_steps" in sec
        ), "TaskH sec should include injection_id or attack/detection/containment fields"

    if method_id in DETERMINISTIC_METHOD_IDS:
        out_path2 = tmp_path / f"results_{method_id}_{task_name}_rerun.json"
        run_benchmark(
            task_name=task_name,
            num_episodes=1,
            base_seed=42,
            out_path=out_path2,
            repo_root=repo_root,
            coord_method=method_id,
            injection_id=injection_id,
            scale_config_override=scale_config,
            pipeline_mode="deterministic",
        )
        d1 = json.loads(out_path.read_text(encoding="utf-8"))
        d2 = json.loads(out_path2.read_text(encoding="utf-8"))
        m1 = (d1.get("episodes") or [{}])[0].get("metrics") or {}
        m2 = (d2.get("episodes") or [{}])[0].get("metrics") or {}
        assert m1.get("throughput") == m2.get("throughput"), "Determinism: throughput must match on rerun"
        assert m1.get("steps") == m2.get("steps"), "Determinism: steps must match on rerun"
        comm1 = (m1.get("coordination") or {}).get("comm") or {}
        comm2 = (m2.get("coordination") or {}).get("comm") or {}
        if "msg_count" in comm1 and "msg_count" in comm2:
            assert comm1["msg_count"] == comm2["msg_count"], "Determinism: comm.msg_count must match on rerun"


def test_coordination_matrix_smoke_gate_info() -> None:
    """When full smoke is off, only baseline methods are run (documentation)."""
    methods = _method_ids_for_matrix()
    if not _coordination_smoke_full():
        assert all(m in BASELINE_METHOD_IDS for m in methods), "Default run should use only baseline subset"
    else:
        assert len(methods) >= len(BASELINE_METHOD_IDS), "Full smoke should include at least baseline methods"
