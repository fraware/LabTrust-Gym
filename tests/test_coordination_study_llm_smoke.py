"""
Smoke test for coordination study with LLM methods: runs 1 cell per LLM method
with deterministic backend, asserts results schema validity and stable summary output.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.summarize import validate_results_v02
from labtrust_gym.studies.coordination_study_runner import (
    LLM_METHOD_IDS,
    run_coordination_study,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _normalize_csv_for_hash(content: str) -> bytes:
    """Normalize line endings so CSV hash is stable across platforms."""
    return content.strip().replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def test_coordination_study_llm_smoke_one_cell_per_method(tmp_path: Path) -> None:
    """Run coordination study with LLM methods and deterministic backend; assert schema and files."""
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
    expected_cells = manifest.get("num_cells", 0)
    assert expected_cells >= 1, manifest
    assert len(cell_ids) == expected_cells

    for cell_id in cell_ids:
        results_path = tmp_path / "cells" / cell_id / "results.json"
        assert results_path.exists(), f"Missing {results_path}"
        data = json.loads(results_path.read_text(encoding="utf-8"))
        assert "schema_version" in data
        assert "task" in data
        assert data.get("task") == "TaskH_COORD_RISK"
        assert "episodes" in data
        assert isinstance(data["episodes"], list)
        assert "seeds" in data
        assert "agent_baseline_id" in data
        method_part = next((m for m in LLM_METHOD_IDS if m in cell_id), None)
        assert method_part is not None, f"Cell {cell_id} should contain an LLM method id"
        meta = data.get("metadata") or {}
        assert meta.get("llm_backend") == "deterministic"
        assert "llm_method_id" in meta
        assert meta["llm_method_id"] == method_part
        assert "results_hash" in meta, "Deterministic run must store results_hash"
        errors = validate_results_v02(data)
        assert not errors, f"Cell {cell_id} results invalid: {errors}"
        # At least one LLM cell must have canonical coordination.llm with call_count
        episodes = data.get("episodes") or []
        if episodes and method_part:
            first_metrics = episodes[0].get("metrics") or {}
            coord = first_metrics.get("coordination") or {}
            llm = coord.get("llm")
            if llm is not None:
                assert "call_count" in llm, f"LLM cell {cell_id} must have coordination.llm.call_count"
                assert "total_tokens" in llm
                assert "invalid_output_rate" in llm
        meta = data.get("metadata") or {}
        if method_part and meta.get("prompt_sha256") is not None:
            assert meta.get("prompt_template_id"), "LLM cell should have prompt_template_id when prompt_sha256 present"
            assert meta.get("allowed_actions_payload_sha256") is not None
            assert meta.get("coordination_policy_fingerprint") is not None

    summary_csv = tmp_path / "summary" / "summary_coord.csv"
    assert summary_csv.exists(), f"Missing {summary_csv}"
    lines = summary_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2
    header = lines[0]
    for col in (
        "proposal_valid_rate",
        "tokens_per_step",
        "p95_llm_latency_ms",
        "cost.total_tokens",
        "cost.estimated_cost_usd",
        "llm.error_rate",
        "llm.invalid_output_rate",
    ):
        assert col in header, f"summary_coord.csv missing column {col}"


def test_coordination_study_llm_smoke_stable_summary(tmp_path: Path) -> None:
    """Rerun LLM study with same seed; summary_coord.csv must be identical (determinism)."""
    repo = _repo_root()
    spec_path = repo / "tests" / "fixtures" / "coordination_study_llm_smoke_spec.yaml"
    if not spec_path.exists():
        pytest.skip(f"Fixture spec not found: {spec_path}")

    os.environ["LABTRUST_REPRO_SMOKE"] = "1"
    try:
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        run_coordination_study(
            spec_path, out1, repo_root=repo, llm_backend="deterministic", llm_model=None
        )
        run_coordination_study(
            spec_path, out2, repo_root=repo, llm_backend="deterministic", llm_model=None
        )
    finally:
        os.environ.pop("LABTRUST_REPRO_SMOKE", None)

    csv1 = out1 / "summary" / "summary_coord.csv"
    csv2 = out2 / "summary" / "summary_coord.csv"
    assert csv1.exists() and csv2.exists()
    raw1 = csv1.read_text(encoding="utf-8")
    raw2 = csv2.read_text(encoding="utf-8")
    h1 = hashlib.sha256(_normalize_csv_for_hash(raw1)).hexdigest()
    h2 = hashlib.sha256(_normalize_csv_for_hash(raw2)).hexdigest()
    assert h1 == h2, "Same seed and llm_backend=deterministic must yield identical summary_coord.csv"

    # Determinism of episode log: same seed -> identical proposal_hash sequence (audit digest)
    cells_dir1 = out1 / "cells"
    cells_dir2 = out2 / "cells"
    if cells_dir1.exists() and cells_dir2.exists():
        for cell_id in (cells_dir1.iterdir() if cells_dir1.is_dir() else []):
            if not cell_id.is_dir():
                continue
            ep_log1 = cell_id / "episodes.jsonl"
            ep_log2 = cells_dir2 / cell_id.name / "episodes.jsonl"
            if not ep_log1.exists() or not ep_log2.exists():
                continue
            steps1 = []
            steps2 = []
            for path, steps in [(ep_log1, steps1), (ep_log2, steps2)]:
                for line in path.read_text(encoding="utf-8").strip().splitlines():
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    if rec.get("log_type") == "LLM_COORD_AUDIT_DIGEST":
                        steps.extend(rec.get("steps") or [])
                        break
            if steps1 or steps2:
                assert steps1 == steps2, (
                    f"Cell {cell_id.name}: same seed must yield identical audit digest steps"
                )
                break


def test_coordination_study_without_llm_backend_excludes_llm_methods(tmp_path: Path) -> None:
    """When llm_backend is not set, only non-LLM methods from spec are run (backward compatible)."""
    repo = _repo_root()
    spec_path = repo / "tests" / "fixtures" / "coordination_study_smoke_spec.yaml"
    if not spec_path.exists():
        pytest.skip(f"Fixture spec not found: {spec_path}")

    os.environ["LABTRUST_REPRO_SMOKE"] = "1"
    try:
        manifest = run_coordination_study(spec_path, tmp_path, repo_root=repo)
    finally:
        os.environ.pop("LABTRUST_REPRO_SMOKE", None)

    cell_ids = manifest.get("cell_ids") or []
    for cell_id in cell_ids:
        assert not any(m in cell_id for m in LLM_METHOD_IDS), (
            f"Without --llm-backend, LLM methods must not run; got cell {cell_id}"
        )
