"""
Baseline regression guard: compare current benchmark run to frozen official baselines.

- Gated by LABTRUST_CHECK_BASELINES=1.
- Prefers benchmarks/baselines_official/v0.2/ (canonical); skips only if v0.2/results/
  is missing or has no *.json (v0.1 is legacy and not used for regression).
- Runs a tiny sweep (episodes=3, seed=123, timing=explicit) for Tasks A–F.
- Loads official results from benchmarks/baselines_official/v0.2/results/*.json.
- Compares exact integer/struct metrics only (stable across OS/Python):
  throughput, holds_count, tokens_minted, tokens_consumed, steps,
  blocked_by_reason_code, violations_by_invariant_id.
  Float metrics (e.g. on_time_rate) are omitted for cross-OS stability.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.baseline_registry import load_official_baseline_registry
from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# Exact metrics to compare (integers and structs only; no floats for cross-OS stability).
EXACT_METRIC_KEYS = [
    "throughput",
    "holds_count",
    "tokens_minted",
    "tokens_consumed",
    "steps",
]
STRUCT_METRIC_KEYS = [
    "blocked_by_reason_code",
    "violations_by_invariant_id",
]


def _normalize_metrics_for_compare(metrics: dict) -> dict:
    """Extract exact-comparison subset; normalize missing/None to canonical form."""
    out = {}
    for k in EXACT_METRIC_KEYS:
        v = metrics.get(k)
        if v is None:
            out[k] = 0
        else:
            out[k] = int(v)
    for k in STRUCT_METRIC_KEYS:
        v = metrics.get(k)
        if v is None or not isinstance(v, dict):
            out[k] = {}
        else:
            out[k] = dict(v)
    return out


def _should_run_regression() -> bool:
    return os.environ.get("LABTRUST_CHECK_BASELINES") == "1"


def test_official_baselines_regression(tmp_path: Path) -> None:
    """
    Compare current run (episodes=3, seed=123, timing=explicit) to frozen official v0.2.

    Prefers v0.2 (canonical); skips only if LABTRUST_CHECK_BASELINES=1 is set and
    benchmarks/baselines_official/v0.2/results/ is missing or has no *.json.
    Compares only exact integer/struct metrics per episode (by seed) for stability.
    """
    if not _should_run_regression():
        pytest.skip("Set LABTRUST_CHECK_BASELINES=1 to run baseline regression guard.")

    repo = _repo_root()
    if not (repo / "policy").is_dir():
        pytest.skip("repo root not found")

    official_results_dir = repo / "benchmarks" / "baselines_official" / "v0.2" / "results"
    if not official_results_dir.is_dir():
        pytest.skip(
            "Official baselines not found at "
            "benchmarks/baselines_official/v0.2/results/; run "
            "labtrust generate-official-baselines --out "
            "benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123"
        )

    official_files = list(official_results_dir.glob("*.json"))
    if not official_files:
        pytest.skip("No official result JSONs in benchmarks/baselines_official/v0.2/results/")

    tasks_in_order, _, task_to_suffix = load_official_baseline_registry(repo)
    episodes = 3
    seed = 123
    timing = "explicit"

    failures = []
    for task in tasks_in_order:
        suffix = task_to_suffix[task]
        official_path = official_results_dir / f"{task}_{suffix}.json"
        if not official_path.exists():
            # Skip tasks that have no committed official baseline yet (e.g. TaskG, TaskH)
            continue

        current_path = tmp_path / f"{task}_{suffix}.json"
        run_benchmark(
            task_name=task,
            num_episodes=episodes,
            base_seed=seed,
            out_path=current_path,
            repo_root=repo,
            log_path=None,
            partner_id=None,
            timing_mode=timing,
        )
        current_data = json.loads(current_path.read_text(encoding="utf-8"))
        official_data = json.loads(official_path.read_text(encoding="utf-8"))

        if official_data.get("schema_version") != "0.2":
            failures.append(
                f"{task}: official file has schema_version {official_data.get('schema_version')!r}, expected 0.2"
            )
            continue
        if not isinstance(official_data.get("episodes"), list):
            failures.append(f"{task}: official file missing or invalid 'episodes' list")
            continue

        current_episodes = {int(ep["seed"]): ep for ep in (current_data.get("episodes") or [])}
        official_episodes = {int(ep["seed"]): ep for ep in (official_data.get("episodes") or [])}

        for ep_seed in range(seed, seed + episodes):
            if ep_seed not in current_episodes:
                failures.append(f"{task} seed {ep_seed}: missing in current run")
                continue
            if ep_seed not in official_episodes:
                failures.append(
                    f"{task} seed {ep_seed}: missing in official (official may have "
                    "been generated with different --episodes/--seed)"
                )
                continue
            cur_metrics = _normalize_metrics_for_compare(current_episodes[ep_seed].get("metrics") or {})
            off_metrics = _normalize_metrics_for_compare(official_episodes[ep_seed].get("metrics") or {})
            for key in EXACT_METRIC_KEYS + STRUCT_METRIC_KEYS:
                if cur_metrics.get(key) != off_metrics.get(key):
                    failures.append(
                        f"{task} seed {ep_seed} {key}: current={cur_metrics.get(key)!r} "
                        f"official={off_metrics.get(key)!r}"
                    )

    if failures:
        pytest.fail("Baseline regression (exact metrics):\n  " + "\n  ".join(failures))
