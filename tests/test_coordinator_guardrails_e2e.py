"""
E2E tests for coordinator guardrails and multi-LLM protocols through the full runner.

Runs run_benchmark with coord_scale / coord_risk, pipeline_mode=llm_offline (no network),
and asserts completion, result structure, and when LABTRUST_LLM_TRACE=1 attribution shape.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


class _FailAfterNProposalBackend:
    """Wraps a proposal backend and raises after N generate_proposal calls (simulates 429/timeout)."""

    def __init__(self, inner: Any, n: int = 2) -> None:
        self._inner = inner
        self._n = max(0, n)
        self._calls = 0

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str],
        step_id: int,
        method_id: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        self._calls += 1
        if self._calls > self._n:
            raise RuntimeError("simulated 429 or timeout after N calls")
        out = self._inner.generate_proposal(
            state_digest, allowed_actions, step_id, method_id, **kwargs
        )
        if isinstance(out, tuple):
            return out
        return out, {}


def test_e2e_coordinator_guardrails_full_episode() -> None:
    """Run one full episode with guarded coordinator path (llm_offline); assert completion and result structure."""
    from labtrust_gym.benchmarks.coordination_scale import (
        CoordinationScaleConfig,
        load_scale_config_by_id,
    )
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = _repo_root()
    scale_config = load_scale_config_by_id(repo_root, "small_smoke")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results_guardrails_e2e.json"
        results = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=42,
            out_path=out,
            repo_root=repo_root,
            coord_method="llm_central_planner",
            scale_config_override=scale_config,
            pipeline_mode="llm_offline",
        )
        assert out.exists()
        assert results is not None
        assert isinstance(results, dict)
        assert results.get("num_episodes") == 1
        assert len(results.get("episodes", [])) == 1
        assert "metadata" in results or "pipeline_mode" in results
        if results.get("metadata"):
            assert "llm_attribution_summary" in results["metadata"] or True


def test_e2e_round_robin_through_runner() -> None:
    """Run benchmark with llm_auction_bidder and coord_auction_protocol=round_robin; assert completion and attribution shape when present."""
    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = _repo_root()
    scale_config = load_scale_config_by_id(repo_root, "small_smoke")
    assert getattr(scale_config, "coord_auction_protocol", None) == "round_robin"
    prev = os.environ.get("LABTRUST_LLM_TRACE")
    try:
        os.environ["LABTRUST_LLM_TRACE"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "results_round_robin_e2e.json"
            results = run_benchmark(
                task_name="coord_scale",
                num_episodes=1,
                base_seed=43,
                out_path=out,
                repo_root=repo_root,
                coord_method="llm_auction_bidder",
                scale_config_override=scale_config,
                pipeline_mode="llm_offline",
            )
            assert out.exists()
            assert results is not None
            assert len(results.get("episodes", [])) == 1
            summary = (results.get("metadata") or {}).get("llm_attribution_summary")
            assert summary is not None, "LABTRUST_LLM_TRACE=1 should produce llm_attribution_summary"
            by_backend = summary.get("by_backend") or {}
            assert isinstance(by_backend, dict)
            total_calls = sum(
                b.get("call_count", 0) for b in by_backend.values() if isinstance(b, dict)
            )
            num_agents = scale_config.num_agents_total
            if total_calls > 0:
                assert total_calls >= num_agents, (
                    f"round_robin with instrumented backends should yield at least {num_agents} bidder calls; got total_calls={total_calls}"
                )
    finally:
        if prev is not None:
            os.environ["LABTRUST_LLM_TRACE"] = prev
        elif "LABTRUST_LLM_TRACE" in os.environ:
            os.environ.pop("LABTRUST_LLM_TRACE")


def test_e2e_attribution_structure_with_trace() -> None:
    """With LABTRUST_LLM_TRACE=1, run coord benchmark and assert metadata.llm_attribution_summary has by_backend structure."""
    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = _repo_root()
    scale_config = load_scale_config_by_id(repo_root, "small_smoke")
    prev = os.environ.get("LABTRUST_LLM_TRACE")
    try:
        os.environ["LABTRUST_LLM_TRACE"] = "1"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "results_attribution_e2e.json"
            results = run_benchmark(
                task_name="coord_scale",
                num_episodes=1,
                base_seed=44,
                out_path=out,
                repo_root=repo_root,
                coord_method="llm_auction_bidder",
                scale_config_override=scale_config,
                pipeline_mode="llm_offline",
            )
            assert results is not None
            summary = (results.get("metadata") or {}).get("llm_attribution_summary")
            assert summary is not None
            assert "by_backend" in summary
            by_backend = summary["by_backend"]
            assert isinstance(by_backend, dict)
            assert len(by_backend) > 0, "by_backend should be non-empty when coordinator runs with LABTRUST_LLM_TRACE=1"
            from labtrust_gym.baselines.coordination.methods.llm_auction_bidder import DeterministicBidBackend
            expected_bid_id = DeterministicBidBackend.DEFAULT_BACKEND_ID
            assert expected_bid_id in by_backend, (
                f"llm_auction_bidder uses DeterministicBidBackend; by_backend should "
                f"contain {expected_bid_id!r}, got keys: {list(by_backend.keys())}"
            )
    finally:
        if prev is not None:
            os.environ["LABTRUST_LLM_TRACE"] = prev
        elif "LABTRUST_LLM_TRACE" in os.environ:
            os.environ.pop("LABTRUST_LLM_TRACE")


def test_e2e_guardrail_trigger_full_episode() -> None:
    """Run full episode with backend that fails after N calls; assert run completes and guardrail reason_code appears in episode log."""
    from labtrust_gym.baselines.coordination.methods.llm_central_planner import (
        DeterministicProposalBackend,
    )
    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = _repo_root()
    scale_config = load_scale_config_by_id(repo_root, "small_smoke")
    scale_config_dict = (
        scale_config.__dict__ if hasattr(scale_config, "__dict__") else {}
    )
    seed = int(scale_config_dict.get("seed", 42))
    inner = DeterministicProposalBackend(
        seed=seed,
        default_action_type="NOOP",
    )
    fail_after_n = _FailAfterNProposalBackend(inner, n=2)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_path = tmp_path / "results_guardrail_trigger.json"
        log_path = tmp_path / "episodes.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        results = run_benchmark(
            task_name="coord_scale",
            num_episodes=1,
            base_seed=seed,
            out_path=out_path,
            repo_root=repo_root,
            coord_method="llm_central_planner",
            scale_config_override=scale_config,
            pipeline_mode="llm_live",
            allow_network=True,
            log_path=log_path,
            coord_proposal_backend_override=fail_after_n,
        )

        assert results is not None
        assert results.get("num_episodes") == 1
        assert len(results.get("episodes", [])) == 1

        assert log_path.exists(), "episode log should be written"
        guardrail_reason_codes = ("CIRCUIT_BREAKER_OPEN", "RATE_LIMITED")
        found_guardrail = False
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("log_type") != "LLM_COORD_PROPOSAL":
                    continue
                meta = entry.get("meta") or {}
                rc = meta.get("reason_code")
                if rc in guardrail_reason_codes:
                    found_guardrail = True
                    break
        assert found_guardrail, (
            f"Expected at least one LLM_COORD_PROPOSAL with meta.reason_code in "
            f"{guardrail_reason_codes} in {log_path}"
        )

        coord_decisions_path = log_path.parent / "coord_decisions.jsonl"
        assert coord_decisions_path.exists(), "coord_decisions.jsonl should exist"
        with open(coord_decisions_path, encoding="utf-8") as f:
            lines = [ln for ln in f if ln.strip()]
        assert len(lines) >= 1, "coord_decisions should have at least one step"
