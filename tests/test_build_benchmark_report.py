"""Regression: report resolves results.json after copying runs across hosts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_build_benchmark_report():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "build_benchmark_report.py"
    spec = importlib.util.spec_from_file_location("build_benchmark_report", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_results_path_falls_back_when_logged_path_missing(tmp_path: Path) -> None:
    mod = _load_build_benchmark_report()
    run_dir = tmp_path / "run"
    scale = "medium_stress_signed_bus"
    method = "centralized_planner"
    cell = run_dir / f"{scale}_{method}_none"
    cell.mkdir(parents=True)
    results = cell / "results.json"
    results.write_text(
        json.dumps(
            {
                "num_episodes": 1,
                "episodes": [{"metrics": {"throughput": 1.5, "steps": 10}}],
            }
        ),
        encoding="utf-8",
    )

    resolved = mod._resolve_results_path(
        run_dir,
        scale,
        method,
        "/home/remote/.../medium_stress_signed_bus_centralized_planner_none/"
        "results.json",
    )
    assert resolved == results
    enrich = mod._enrich_results(resolved)
    assert enrich is not None
    assert enrich.get("mean_throughput") == 1.5
    assert enrich.get("mean_steps") == 10.0


def test_build_rows_enriches_with_stale_log_path(tmp_path: Path) -> None:
    mod = _load_build_benchmark_report()
    run_dir = tmp_path / "run"
    scale = "medium_stress_signed_bus"
    method = "centralized_planner"
    cell = run_dir / f"{scale}_{method}_none"
    cell.mkdir(parents=True)
    (cell / "results.json").write_text(
        json.dumps(
            {
                "num_episodes": 2,
                "pipeline_mode": "llm_live",
                "llm_model_id": None,
                "episodes": [
                    {"metrics": {"throughput": 2.0, "steps": 5}},
                    {"metrics": {"throughput": 4.0, "steps": 7}},
                ],
            }
        ),
        encoding="utf-8",
    )
    status = run_dir / "method_status.jsonl"
    line = json.dumps(
        {
            "event": "method_end",
            "method": method,
            "status": "PASS",
            "ended_at": "2026-01-01T00:00:00+00:00",
            "result_path": "/totally/wrong/path/results.json",
        }
    )
    status.write_text(line + "\n", encoding="utf-8")

    rows = mod.build_rows(run_dir, scale, (method,))
    assert len(rows) == 1
    assert rows[0]["status"] == "PASS"
    assert rows[0]["result_path"] is not None
    en = rows[0].get("enrich") or {}
    assert en.get("mean_throughput") == 3.0
    assert en.get("num_episodes") == 2
