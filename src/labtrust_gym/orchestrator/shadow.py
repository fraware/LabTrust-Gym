"""
Shadow mode: run baseline and candidate side-by-side from the same initial
conditions (task, seed), compare step-by-step, and produce shadow_comparison.json
with the same diff schema as replay (status, first_divergence_step, diffs).
"""  # noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.export.receipts import load_episode_log
from labtrust_gym.orchestrator.replay import (
    _find_reference_log,
    _load_results_json,
    compare_episode_logs,
)


def _run_one_episode(
    task_name: str,
    seed: int,
    coord_method: str | None,
    out_dir: Path,
    policy_root: Path,
    config: dict[str, Any],
) -> Path | None:
    """Run one episode with given config; return path to episode log."""
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "episode_log_shadow.jsonl"
    results_path = out_dir / "results_shadow.json"
    try:
        from labtrust_gym.benchmarks.runner import run_benchmark

        run_benchmark(
            task_name=task_name,
            num_episodes=1,
            base_seed=seed,
            out_path=results_path,
            log_path=log_path,
            repo_root=policy_root,
            coord_method=coord_method,
            timing_mode=config.get("timing_mode"),
        )
        return log_path if log_path.exists() else None
    except Exception:
        return None


def run_shadow(
    baseline_run_dir: Path,
    shadow_method_id: str,
    out_dir: Path,
    policy_root: Path,
    compare_metric: str = "action_index",
) -> dict[str, Any]:
    """
    Load baseline run, run one episode with shadow_method_id (same task/seed),
    compare baseline log vs shadow log. Produce shadow_comparison.json.

    baseline_run_dir: directory with episode_log.jsonl (or episode_0.jsonl) and
        results.json (task, seeds, config).
    shadow_method_id: coordination method id for the candidate run (e.g.
        centralized_planner); baseline uses config from results.json (may be None).
    compare_metric: reserved (e.g. action_index); comparison uses full step diff.

    Returns dict with shadow_run_dir, comparison_path (JSON), drift_summary
    (steps_compared, steps_differed, status, first_divergence_step, diffs).
    No sentinel status; artifacts contain real comparisons.
    """
    baseline_run_dir = Path(baseline_run_dir).resolve()
    out_dir = Path(out_dir).resolve()
    policy_root = Path(policy_root or ".").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_log_path = _find_reference_log(baseline_run_dir)
    if ref_log_path is None:
        comparison_path = out_dir / "shadow_comparison.json"
        payload = {
            "status": "failed",
            "first_divergence_step": None,
            "steps_compared": 0,
            "steps_differed": 0,
            "diffs": [],
            "artifact_pointers": {
                "baseline_log": None,
                "shadow_log": None,
                "baseline_run_dir": str(baseline_run_dir),
            },
            "message": ("baseline_run_dir has no episode_log.jsonl or episode_0.jsonl"),
        }
        comparison_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {
            "shadow_run_dir": str(out_dir),
            "comparison_path": str(comparison_path),
            "drift_summary": {
                "steps_compared": 0,
                "steps_differed": 0,
                "status": "failed",
                "first_divergence_step": None,
            },
        }

    ref_entries = load_episode_log(ref_log_path)
    results = _load_results_json(baseline_run_dir)
    if not results:
        comparison_path = out_dir / "shadow_comparison.json"
        payload = {
            "status": "failed",
            "first_divergence_step": None,
            "steps_compared": 0,
            "steps_differed": 0,
            "diffs": [],
            "artifact_pointers": {
                "baseline_log": str(ref_log_path),
                "shadow_log": None,
                "baseline_run_dir": str(baseline_run_dir),
            },
            "message": "baseline_run_dir has no results.json",
        }
        comparison_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {
            "shadow_run_dir": str(out_dir),
            "comparison_path": str(comparison_path),
            "drift_summary": {
                "steps_compared": 0,
                "steps_differed": 0,
                "status": "failed",
                "first_divergence_step": None,
            },
        }

    task_name = results.get("task")
    seeds = results.get("seeds")
    config = results.get("config") or {}
    if not task_name or not seeds:
        comparison_path = out_dir / "shadow_comparison.json"
        payload = {
            "status": "failed",
            "first_divergence_step": None,
            "steps_compared": 0,
            "steps_differed": 0,
            "diffs": [],
            "artifact_pointers": {
                "baseline_log": str(ref_log_path),
                "shadow_log": None,
                "baseline_run_dir": str(baseline_run_dir),
            },
            "message": "results.json missing task or seeds",
        }
        comparison_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {
            "shadow_run_dir": str(out_dir),
            "comparison_path": str(comparison_path),
            "drift_summary": {
                "steps_compared": 0,
                "steps_differed": 0,
                "status": "failed",
                "first_divergence_step": None,
            },
        }

    seed = int(seeds[0])
    shadow_log_path = _run_one_episode(task_name, seed, shadow_method_id, out_dir, policy_root, config)
    if shadow_log_path is None:
        comparison_path = out_dir / "shadow_comparison.json"
        payload = {
            "status": "failed",
            "first_divergence_step": None,
            "steps_compared": len(ref_entries),
            "steps_differed": 0,
            "diffs": [],
            "artifact_pointers": {
                "baseline_log": str(ref_log_path),
                "shadow_log": None,
                "baseline_run_dir": str(baseline_run_dir),
            },
            "message": "shadow run (re-execute) failed",
        }
        comparison_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {
            "shadow_run_dir": str(out_dir),
            "comparison_path": str(comparison_path),
            "drift_summary": {
                "steps_compared": len(ref_entries),
                "steps_differed": 0,
                "status": "failed",
                "first_divergence_step": None,
            },
        }

    run_entries = load_episode_log(shadow_log_path)
    comparison = compare_episode_logs(ref_entries, run_entries)
    steps_differed = len(comparison["diffs"])

    payload = {
        "status": comparison["status"],
        "first_divergence_step": comparison["first_divergence_step"],
        "steps_compared": comparison["steps_compared"],
        "steps_differed": steps_differed,
        "diffs": comparison["diffs"],
        "receipt_digests_match": comparison.get("receipt_digests_match"),
        "artifact_pointers": {
            "baseline_log": str(ref_log_path),
            "shadow_log": str(shadow_log_path),
            "baseline_run_dir": str(baseline_run_dir),
        },
        "shadow_method_id": shadow_method_id,
        "compare_metric": compare_metric,
    }
    comparison_path = out_dir / "shadow_comparison.json"
    comparison_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "shadow_run_dir": str(out_dir),
        "comparison_path": str(comparison_path),
        "drift_summary": {
            "steps_compared": comparison["steps_compared"],
            "steps_differed": steps_differed,
            "status": comparison["status"],
            "first_divergence_step": comparison["first_divergence_step"],
        },
    }
