"""
Unit and integration tests for LLM economics in coordination benchmarks:
- Aggregator fills 0/null for missing coordination.llm (non-LLM methods).
- LLM method runs produce canonical coordination.llm and summary columns.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from labtrust_gym.studies.coordination_study_runner import (
    _aggregate_cell_metrics,
    _empty_cell_metrics,
    _write_summary_csv,
    run_coordination_study,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_empty_cell_metrics_includes_llm_economics_keys() -> None:
    """_empty_cell_metrics returns cost and llm economics keys with 0/null."""
    out = _empty_cell_metrics()
    assert out.get("cost.total_tokens") == 0
    assert out.get("cost.estimated_cost_usd") is None
    assert out.get("llm.error_rate") == 0.0
    assert out.get("llm.invalid_output_rate") is None


def test_aggregate_cell_metrics_missing_llm_fills_zero_null() -> None:
    """When episodes have no coordination.llm, aggregator sets cost/llm to 0 or null."""
    episodes = [
        {
            "metrics": {
                "throughput": 1,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "steps": 10,
            },
        },
        {
            "metrics": {
                "throughput": 2,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "steps": 10,
            },
        },
    ]
    out = _aggregate_cell_metrics(episodes)
    assert out["cost.total_tokens"] == 0
    assert out["cost.estimated_cost_usd"] is None
    assert out["llm.error_rate"] == 0.0
    assert out["llm.invalid_output_rate"] is None


def test_aggregate_cell_metrics_with_llm_economics() -> None:
    """When episodes have coordination.llm with canonical keys, aggregator sums/means them."""
    episodes = [
        {
            "metrics": {
                "throughput": 1,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "steps": 5,
                "coordination": {
                    "llm": {
                        "call_count": 5,
                        "total_tokens": 100,
                        "tokens_per_step": 20.0,
                        "mean_latency_ms": 50.0,
                        "p95_latency_ms": 80.0,
                        "latency_ms": 50.0,
                        "error_rate": 0.0,
                        "invalid_output_rate": 0.1,
                        "estimated_cost_usd": 0.002,
                    },
                },
            },
        },
        {
            "metrics": {
                "throughput": 2,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "steps": 5,
                "coordination": {
                    "llm": {
                        "call_count": 5,
                        "total_tokens": 150,
                        "tokens_per_step": 30.0,
                        "mean_latency_ms": 60.0,
                        "p95_latency_ms": 90.0,
                        "latency_ms": 60.0,
                        "error_rate": 0.0,
                        "invalid_output_rate": 0.2,
                        "estimated_cost_usd": 0.003,
                    },
                },
            },
        },
    ]
    out = _aggregate_cell_metrics(episodes)
    assert out["cost.total_tokens"] == 250
    assert out["cost.estimated_cost_usd"] == pytest.approx(0.005)
    assert out["llm.error_rate"] == 0.0
    assert out["llm.invalid_output_rate"] == pytest.approx(0.15)
    assert out["tokens_per_step"] == pytest.approx(25.0)
    assert out["p95_llm_latency_ms"] is not None


def test_aggregate_cell_metrics_sec_rate_ci_and_worst_case() -> None:
    """_aggregate_cell_metrics returns sec.attack_success_rate CI and worst_case when n >= 1."""
    # Two episodes: one with attack success, one without -> rate 0.5
    episodes = [
        {
            "metrics": {
                "throughput": 1,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "sec": {"attack_success_rate": 1.0, "attack_success_observed": 1.0},
            },
        },
        {
            "metrics": {
                "throughput": 1,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "sec": {"attack_success_rate": 0.0, "attack_success_observed": 0.0},
            },
        },
    ]
    out = _aggregate_cell_metrics(episodes)
    assert out["sec.attack_success_rate"] == 0.5
    assert out["sec.attack_success_rate_ci_lower"] is not None
    assert out["sec.attack_success_rate_ci_upper"] is not None
    assert out["sec.attack_success_rate_ci_lower"] <= 0.5 <= out["sec.attack_success_rate_ci_upper"]
    # 0 successes in 2 episodes -> worst_case not set (we have 1 success). When 0 successes, worst_case is set.
    episodes_zero = [
        {
            "metrics": {
                "throughput": 0,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "sec": {"attack_success_rate": 0.0},
            }
        },
        {
            "metrics": {
                "throughput": 0,
                "violations_by_invariant_id": {},
                "blocked_by_reason_code": {},
                "sec": {"attack_success_rate": 0.0},
            }
        },
    ]
    out_zero = _aggregate_cell_metrics(episodes_zero)
    assert out_zero["sec.attack_success_rate"] == 0.0
    assert out_zero["sec.worst_case_attack_success_upper_95"] is not None
    assert 0 < out_zero["sec.worst_case_attack_success_upper_95"] < 1.0


def test_coordination_study_llm_cell_has_llm_economics_and_summary_columns(
    tmp_path: Path,
) -> None:
    """One TaskH cell with an LLM method produces non-null llm.call_count and valid summary row with new columns."""
    repo = _repo_root()
    spec_path = repo / "tests" / "fixtures" / "coordination_study_llm_smoke_spec.yaml"
    if not spec_path.exists():
        pytest.skip(f"Fixture spec not found: {spec_path}")

    os.environ["LABTRUST_REPRO_SMOKE"] = "1"
    try:
        manifest = run_coordination_study(
            spec_path,
            tmp_path,
            repo_root=repo,
            llm_backend="deterministic",
            llm_model=None,
        )
    finally:
        os.environ.pop("LABTRUST_REPRO_SMOKE", None)

    cell_ids = manifest.get("cell_ids") or []
    assert cell_ids, "Expected at least one cell"

    # Find first cell that has episodes with coordination.llm (any LLM method in spec)
    found_llm_cell = False
    for cell_id in cell_ids:
        results_path = tmp_path / "cells" / cell_id / "results.json"
        if not results_path.exists():
            continue
        data = json.loads(results_path.read_text(encoding="utf-8"))
        episodes = data.get("episodes") or []
        for ep in episodes:
            m = ep.get("metrics") or {}
            coord = m.get("coordination") or {}
            llm = coord.get("llm")
            if llm is not None and llm.get("call_count") is not None:
                assert isinstance(llm.get("call_count"), (int, float))
                assert "total_tokens" in llm
                assert "tokens_per_step" in llm
                assert "invalid_output_rate" in llm
                found_llm_cell = True
                break
        if found_llm_cell:
            break

    assert found_llm_cell, "At least one cell should have episodes with coordination.llm.call_count"

    summary_csv = tmp_path / "summary" / "summary_coord.csv"
    assert summary_csv.exists()
    content = summary_csv.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert len(lines) >= 2
    header = lines[0]
    for col in (
        "cost.total_tokens",
        "cost.estimated_cost_usd",
        "llm.error_rate",
        "llm.invalid_output_rate",
    ):
        assert col in header, f"summary_coord.csv must include column {col}"

    # Summary rows exist and include the new columns (values may be 0 or empty for deterministic runs).
    # Rows can exceed cell count when one injection maps to multiple risk_ids.
    import csv as csv_module
    from io import StringIO

    reader = csv_module.DictReader(StringIO(content))
    data_rows = list(reader)
    assert len(data_rows) >= len(cell_ids), (
        f"summary_coord.csv must have at least one row per cell: {len(data_rows)} rows, {len(cell_ids)} cells"
    )
    for row in data_rows:
        assert "cost.total_tokens" in row
        assert "llm.error_rate" in row
    assert "p95_llm_latency_ms" in header, "summary_coord.csv must include p95_llm_latency_ms (3a.2 contract)"


def test_write_summary_csv_always_has_cost_and_latency_columns(tmp_path: Path) -> None:
    """_write_summary_csv always writes cost.estimated_cost_usd and p95_llm_latency_ms columns (3a.2)."""
    csv_path = tmp_path / "summary_coord.csv"
    rows = [
        {
            "method_id": "centralized_planner",
            "scale_id": "small_smoke",
            "injection_id": "none",
            "cost.estimated_cost_usd": None,
            "p95_llm_latency_ms": None,
        },
        {
            "method_id": "llm_central_planner",
            "scale_id": "small_smoke",
            "injection_id": "none",
            "cost.estimated_cost_usd": 0.01,
            "p95_llm_latency_ms": 100.0,
        },
    ]
    _write_summary_csv(csv_path, rows)
    content = csv_path.read_text(encoding="utf-8")
    header = content.splitlines()[0]
    assert "cost.estimated_cost_usd" in header
    assert "p95_llm_latency_ms" in header
