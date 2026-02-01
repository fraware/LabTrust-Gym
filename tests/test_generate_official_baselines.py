"""
Smoke tests for generate-official-baselines CLI.

- Output files exist (results/Task*_*.json, summary.csv, summary.md, metadata.json).
- Results validate against results.v0.2.schema.json.
- summarize-results runs and produces tables.
- Rerun with same args (explicit timing) yields identical episode metrics.
- Overwrite refusal without --force.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.baseline_registry import load_official_baseline_registry
from labtrust_gym.benchmarks.summarize import validate_results_v02
from labtrust_gym.cli.main import _run_generate_official_baselines  # noqa: E402


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_generate_official_baselines_smoke(tmp_path: Path) -> None:
    """Run generate-official-baselines with 2 episodes per task; assert output files exist, schema validates, summary produced."""
    repo = _repo_root()
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")

    tasks_in_order, _, task_to_suffix = load_official_baseline_registry(repo)

    out_dir = tmp_path / "v0.2"
    args = SimpleNamespace(
        out=str(out_dir),
        episodes=2,
        seed=123,
        timing="explicit",
        partner=None,
        force=True,
    )
    exit_code = _run_generate_official_baselines(args)
    assert exit_code == 0, "generate-official-baselines should exit 0"

    results_dir = out_dir / "results"
    assert results_dir.is_dir(), "results/ directory should exist"

    schema_path = repo / "policy" / "schemas" / "results.v0.2.schema.json"
    if not schema_path.exists():
        pytest.skip("results.v0.2.schema.json not found")

    for task in tasks_in_order:
        suffix = task_to_suffix[task]
        result_path = results_dir / f"{task}_{suffix}.json"
        assert result_path.exists(), f"Result file should exist: {result_path}"
        data = json.loads(result_path.read_text(encoding="utf-8"))
        errors = validate_results_v02(data, schema_path=schema_path)
        assert errors == [], f"{result_path} should validate: {errors}"

    summary_csv = out_dir / "summary.csv"
    summary_md = out_dir / "summary.md"
    assert summary_csv.exists(), "summary.csv should exist"
    assert summary_md.exists(), "summary.md should exist"

    csv_lines = summary_csv.read_text(encoding="utf-8").strip().splitlines()
    assert len(csv_lines) >= 2, "summary.csv should have header + at least one data row"
    h = csv_lines[0].lower()
    assert "task" in h or "throughput" in h, "summary.csv should have table header"

    md_content = summary_md.read_text(encoding="utf-8")
    assert "|" in md_content or "task" in md_content.lower(), "summary.md should contain table content"

    metadata_path = out_dir / "metadata.json"
    assert metadata_path.exists(), "metadata.json should exist"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata.get("version") == "0.2"
    assert "cli_args" in metadata
    assert metadata["cli_args"].get("episodes") == 2
    assert metadata["cli_args"].get("seed") == 123
    assert metadata["cli_args"].get("timing") == "explicit"
    assert set(metadata.get("tasks", [])) == set(tasks_in_order)
    assert "timestamp" in metadata
    assert "baseline_ids" in metadata


def test_generate_official_baselines_determinism_explicit_timing(tmp_path: Path) -> None:
    """Rerun with same args (explicit timing, fixed seed) yields identical episode metrics."""
    repo = _repo_root()
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")

    tasks_in_order, _, task_to_suffix = load_official_baseline_registry(repo)
    task = tasks_in_order[0]
    suffix = task_to_suffix[task]

    base_args = dict(
        episodes=2,
        seed=123,
        timing="explicit",
        partner=None,
        force=True,
    )

    out1 = tmp_path / "run1"
    exit1 = _run_generate_official_baselines(SimpleNamespace(out=str(out1), **base_args))
    assert exit1 == 0

    out2 = tmp_path / "run2"
    exit2 = _run_generate_official_baselines(SimpleNamespace(out=str(out2), **base_args))
    assert exit2 == 0

    path1 = out1 / "results" / f"{task}_{suffix}.json"
    path2 = out2 / "results" / f"{task}_{suffix}.json"
    assert path1.exists() and path2.exists()

    data1 = json.loads(path1.read_text(encoding="utf-8"))
    data2 = json.loads(path2.read_text(encoding="utf-8"))
    eps1 = data1.get("episodes") or []
    eps2 = data2.get("episodes") or []
    assert len(eps1) == len(eps2) == 2, "expected 2 episodes"
    for i, (e1, e2) in enumerate(zip(eps1, eps2)):
        assert e1.get("seed") == e2.get("seed"), f"episode {i} seed mismatch"
        m1 = e1.get("metrics") or {}
        m2 = e2.get("metrics") or {}
        assert m1.get("throughput") == m2.get("throughput"), (
            f"episode {i} throughput mismatch"
        )
        assert m1.get("steps") == m2.get("steps"), f"episode {i} steps mismatch"


def test_generate_official_baselines_refuses_overwrite_without_force(tmp_path: Path) -> None:
    """Without --force, generate-official-baselines refuses to overwrite existing dir."""
    repo = _repo_root()
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")

    out_dir = tmp_path / "v0.2"
    out_dir.mkdir(parents=True)
    (out_dir / "results").mkdir()
    (out_dir / "metadata.json").write_text("{}")

    args = SimpleNamespace(
        out=str(out_dir),
        episodes=2,
        seed=123,
        timing="explicit",
        partner=None,
        force=False,
    )
    exit_code = _run_generate_official_baselines(args)
    assert exit_code == 1, "Should exit 1 when dir exists and --force not set"
