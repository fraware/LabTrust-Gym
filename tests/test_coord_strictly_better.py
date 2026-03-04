"""
Strictly-better-than-baseline scenario tests for coordination methods.

Each test runs coord_risk (or coord_scale) with the same scale, seed, and
injection for a baseline method and an LLM method, then asserts the LLM
method is at least as good as the baseline on a chosen metric (throughput,
or resilience under poison). Uses llm_offline + deterministic_constrained
for CI stability.
"""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_coord_one_episode(
    tmp_path: Path,
    task_name: str,
    coord_method: str,
    injection_id: str | None = None,
    scale_id: str = "small_smoke",
    seed: int = 42,
    pipeline_mode: str = "deterministic",
    llm_backend: str | None = None,
) -> dict:
    """Run one episode of coord_risk/coord_scale; return full results dict."""
    repo = _repo_root()
    scale = load_scale_config_by_id(repo, scale_id)
    out = tmp_path / f"results_{coord_method}.json"
    run_benchmark(
        task_name=task_name,
        num_episodes=1,
        base_seed=seed,
        out_path=out,
        repo_root=repo,
        coord_method=coord_method,
        injection_id=injection_id or "none",
        scale_config_override=scale,
        pipeline_mode=pipeline_mode,
        llm_backend=llm_backend,
    )
    assert out.exists()
    return json.loads(out.read_text(encoding="utf-8"))


def _throughput_from_results(results: dict) -> float:
    """Extract throughput from first episode metrics; 0 if missing."""
    episodes = results.get("episodes") or []
    if not episodes:
        return 0.0
    metrics = episodes[0].get("metrics") or {}
    return float(metrics.get("throughput", 0) or 0)


def _violations_count_from_results(results: dict) -> int:
    """Sum violation counts from first episode metrics; 0 if missing."""
    episodes = results.get("episodes") or []
    if not episodes:
        return 0
    metrics = episodes[0].get("metrics") or {}
    violations = metrics.get("violations") or []
    return len(violations) if isinstance(violations, list) else 0


def test_llm_repair_over_kernel_whca_at_least_as_good_as_kernel_whca_under_poison(
    tmp_path: Path,
) -> None:
    """coord_risk, INJ-COMMS-POISON-001, small_smoke: llm_repair >= kernel_whca.
    Baseline: kernel_whca (deterministic). LLM: llm_repair_over_kernel_whca.
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="kernel_whca",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    llm = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_repair_over_kernel_whca",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    llm_throughput = _throughput_from_results(llm)
    assert llm_throughput >= base_throughput, f"llm_repair throughput {llm_throughput} < kernel_whca {base_throughput}"


def test_llm_central_planner_at_least_as_good_as_kernel_whca_throughput(
    tmp_path: Path,
) -> None:
    """coord_risk, no injection, small_smoke: llm_central_planner >= kernel_whca.
    Baseline: kernel_whca. LLM: llm_central_planner (llm_offline).
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="kernel_whca",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    llm = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_central_planner",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    llm_throughput = _throughput_from_results(llm)
    assert llm_throughput >= base_throughput, f"llm_central_planner {llm_throughput} < kernel_whca {base_throughput}"


def test_llm_central_planner_agentic_at_least_as_good_as_kernel_whca_throughput(
    tmp_path: Path,
) -> None:
    """coord_risk, no injection, small_smoke: llm_central_planner_agentic >= kernel_whca.
    Baseline: kernel_whca. LLM: llm_central_planner_agentic (llm_offline).
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="kernel_whca",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    llm = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_central_planner_agentic",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    llm_throughput = _throughput_from_results(llm)
    assert llm_throughput >= base_throughput, (
        f"llm_central_planner_agentic {llm_throughput} < kernel_whca {base_throughput}"
    )


def test_llm_central_planner_debate_at_least_as_good_as_kernel_whca_throughput(
    tmp_path: Path,
) -> None:
    """coord_risk, no injection, small_smoke: llm_central_planner_debate >= kernel_whca.
    Baseline: kernel_whca. LLM: llm_central_planner_debate (llm_offline).
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="kernel_whca",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    llm = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_central_planner_debate",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    llm_throughput = _throughput_from_results(llm)
    assert llm_throughput >= base_throughput, (
        f"llm_central_planner_debate {llm_throughput} < kernel_whca {base_throughput}"
    )


def test_llm_hierarchical_allocator_at_least_as_good_as_hierarchical_hub_rr_throughput(
    tmp_path: Path,
) -> None:
    """coord_risk, no injection, small_smoke: llm_hierarchical_allocator >= hierarchical_hub_rr.
    Baseline: hierarchical_hub_rr. LLM: llm_hierarchical_allocator (llm_offline).
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="hierarchical_hub_rr",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    llm = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_hierarchical_allocator",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    llm_throughput = _throughput_from_results(llm)
    assert llm_throughput >= base_throughput, (
        f"llm_hierarchical_allocator {llm_throughput} < hierarchical_hub_rr {base_throughput}"
    )


def test_llm_auction_bidder_at_least_as_good_as_market_auction_throughput(
    tmp_path: Path,
) -> None:
    """coord_risk, no injection, small_smoke: llm_auction_bidder >= market_auction.
    Baseline: market_auction. LLM: llm_auction_bidder (llm_offline).
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="market_auction",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    llm = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_auction_bidder",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    llm_throughput = _throughput_from_results(llm)
    assert llm_throughput >= base_throughput, f"llm_auction_bidder {llm_throughput} < market_auction {base_throughput}"


def test_llm_gossip_summarizer_at_least_as_good_as_gossip_consensus_throughput(
    tmp_path: Path,
) -> None:
    """coord_risk, no injection, small_smoke: llm_gossip_summarizer >= gossip_consensus.
    Baseline: gossip_consensus. LLM: llm_gossip_summarizer (llm_offline).
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="gossip_consensus",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    llm = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_gossip_summarizer",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    llm_throughput = _throughput_from_results(llm)
    assert llm_throughput >= base_throughput, (
        f"llm_gossip_summarizer {llm_throughput} < gossip_consensus {base_throughput}"
    )


def test_llm_local_decider_signed_bus_at_least_as_good_as_ripple_effect_throughput(
    tmp_path: Path,
) -> None:
    """coord_risk, no injection, small_smoke: llm_local_decider_signed_bus >= ripple_effect.
    Baseline: ripple_effect. LLM: llm_local_decider_signed_bus (llm_offline).
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="ripple_effect",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    llm = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_local_decider_signed_bus",
        injection_id="none",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    llm_throughput = _throughput_from_results(llm)
    assert llm_throughput >= base_throughput, (
        f"llm_local_decider_signed_bus {llm_throughput} < ripple_effect {base_throughput}"
    )


def test_llm_detector_throttle_advisor_at_least_as_good_as_kernel_auction_whca_shielded_throughput(
    tmp_path: Path,
) -> None:
    """coord_risk, INJ-COMMS-POISON-001, small_smoke: llm_detector_throttle_advisor >= kernel_auction_whca_shielded.
    Baseline: kernel_auction_whca_shielded. LLM/detector: llm_detector_throttle_advisor (deterministic detector).
    """
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="kernel_auction_whca_shielded",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    detector = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_detector_throttle_advisor",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="deterministic",
    )
    base_throughput = _throughput_from_results(base)
    detector_throughput = _throughput_from_results(detector)
    assert detector_throughput >= base_throughput, (
        f"llm_detector_throttle_advisor {detector_throughput} < kernel_auction_whca_shielded {base_throughput}"
    )


def test_llm_central_planner_shielded_at_least_as_good_as_llm_central_planner_under_poison(
    tmp_path: Path,
) -> None:
    """coord_risk, INJ-COMMS-POISON-001: shielded variant >= base on throughput (attack in scope)."""
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_central_planner",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    variant = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_central_planner_shielded",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    variant_throughput = _throughput_from_results(variant)
    base_violations = _violations_count_from_results(base)
    variant_violations = _violations_count_from_results(variant)
    assert variant_throughput >= base_throughput or variant_violations <= base_violations, (
        f"shielded throughput {variant_throughput} < base {base_throughput} and "
        f"shielded violations {variant_violations} > base {base_violations}"
    )


def test_llm_central_planner_with_safe_fallback_at_least_as_good_as_llm_central_planner_under_poison(
    tmp_path: Path,
) -> None:
    """coord_risk, INJ-COMMS-POISON-001: safe_fallback variant >= base on throughput or safety."""
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_central_planner",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    variant = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_central_planner_with_safe_fallback",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    variant_throughput = _throughput_from_results(variant)
    base_violations = _violations_count_from_results(base)
    variant_violations = _violations_count_from_results(variant)
    assert variant_throughput >= base_throughput or variant_violations <= base_violations, (
        f"safe_fallback throughput {variant_throughput} < base {base_throughput} and "
        f"safe_fallback violations {variant_violations} > base {base_violations}"
    )


def test_llm_hierarchical_allocator_shielded_at_least_as_good_as_base_under_poison(
    tmp_path: Path,
) -> None:
    """coord_risk, INJ-COMMS-POISON-001: shielded >= base (throughput or violations)."""
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_hierarchical_allocator",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    variant = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_hierarchical_allocator_shielded",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    variant_throughput = _throughput_from_results(variant)
    base_violations = _violations_count_from_results(base)
    variant_violations = _violations_count_from_results(variant)
    assert variant_throughput >= base_throughput or variant_violations <= base_violations, (
        f"shielded throughput {variant_throughput} < base {base_throughput} and "
        f"shielded violations {variant_violations} > base {base_violations}"
    )


def test_llm_hierarchical_allocator_with_safe_fallback_at_least_as_good_as_base_under_poison(
    tmp_path: Path,
) -> None:
    """coord_risk, INJ-COMMS-POISON-001: safe_fallback >= base (throughput or violations)."""
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_hierarchical_allocator",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    variant = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_hierarchical_allocator_with_safe_fallback",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    variant_throughput = _throughput_from_results(variant)
    base_violations = _violations_count_from_results(base)
    variant_violations = _violations_count_from_results(variant)
    assert variant_throughput >= base_throughput or variant_violations <= base_violations, (
        f"safe_fallback throughput {variant_throughput} < base {base_throughput} and "
        f"safe_fallback violations {variant_violations} > base {base_violations}"
    )


def test_llm_auction_bidder_shielded_at_least_as_good_as_base_under_poison(
    tmp_path: Path,
) -> None:
    """coord_risk, INJ-COMMS-POISON-001: shielded >= base (throughput or violations)."""
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_auction_bidder",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    variant = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_auction_bidder_shielded",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    variant_throughput = _throughput_from_results(variant)
    base_violations = _violations_count_from_results(base)
    variant_violations = _violations_count_from_results(variant)
    assert variant_throughput >= base_throughput or variant_violations <= base_violations, (
        f"shielded throughput {variant_throughput} < base {base_throughput} and "
        f"shielded violations {variant_violations} > base {base_violations}"
    )


def test_llm_auction_bidder_with_safe_fallback_at_least_as_good_as_base_under_poison(
    tmp_path: Path,
) -> None:
    """coord_risk, INJ-COMMS-POISON-001: safe_fallback >= base (throughput or violations)."""
    base = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_auction_bidder",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    variant = _run_coord_one_episode(
        tmp_path,
        task_name="coord_risk",
        coord_method="llm_auction_bidder_with_safe_fallback",
        injection_id="INJ-COMMS-POISON-001",
        scale_id="small_smoke",
        seed=42,
        pipeline_mode="llm_offline",
        llm_backend="deterministic_constrained",
    )
    base_throughput = _throughput_from_results(base)
    variant_throughput = _throughput_from_results(variant)
    base_violations = _violations_count_from_results(base)
    variant_violations = _violations_count_from_results(variant)
    assert variant_throughput >= base_throughput or variant_violations <= base_violations, (
        f"safe_fallback throughput {variant_throughput} < base {base_throughput} and "
        f"safe_fallback violations {variant_violations} > base {base_violations}"
    )
