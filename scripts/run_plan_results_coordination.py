#!/usr/bin/env python3
"""
Run a fixed coordination scenario to produce a plan-results artifact.

Runs coord_scale with llm_auction_bidder, scale small_smoke (round_robin),
1-2 episodes, pipeline_mode=llm_offline. Writes results.json and a short
summary (plan_results_coordination_summary.json + .md) for the improvement plan.

Usage:
  python scripts/run_plan_results_coordination.py [--out-dir DIR]
  LABTRUST_LLM_TRACE=1 python scripts/run_plan_results_coordination.py  # include attribution

Output:
  <out_dir>/results.json, plan_results_coordination_summary.json, plan_results_coordination_summary.md
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run plan-results coordination scenario")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("labtrust_runs/plan_results_coordination"),
        help="Output directory for results and summary",
    )
    parser.add_argument("--episodes", type=int, default=2, help="Number of episodes")
    parser.add_argument("--seed", type=int, default=100, help="Base seed")
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.json"

    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = Path(__file__).resolve().parent.parent
    scale_config = load_scale_config_by_id(repo_root, "small_smoke")

    results = run_benchmark(
        task_name="coord_scale",
        num_episodes=args.episodes,
        base_seed=args.seed,
        out_path=results_path,
        repo_root=repo_root,
        coord_method="llm_auction_bidder",
        scale_config_override=scale_config,
        pipeline_mode="llm_offline",
    )
    if not results:
        return 1

    metadata = results.get("metadata") or {}
    summary_data = {
        "scenario": "coord_scale llm_auction_bidder small_smoke (round_robin)",
        "pipeline_mode": results.get("pipeline_mode"),
        "num_episodes": results.get("num_episodes"),
        "base_seed": args.seed,
        "scale_id": "small_smoke",
        "coord_auction_protocol": getattr(scale_config, "coord_auction_protocol", None),
        "episode_metrics_sample": [],
        "llm_attribution_present": "llm_attribution_summary" in metadata,
    }
    for i, ep in enumerate(results.get("episodes", [])[:2]):
        m = (ep.get("metrics") or {}).copy()
        summary_data["episode_metrics_sample"].append({"episode": i, "metrics": m})
    if metadata.get("llm_attribution_summary"):
        summary_data["by_backend_call_counts"] = {
            k: v.get("call_count", 0)
            for k, v in (metadata["llm_attribution_summary"].get("by_backend") or {}).items()
            if isinstance(v, dict)
        }

    summary_json_path = out_dir / "plan_results_coordination_summary.json"
    summary_json_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    summary_md_lines = [
        "# Plan results: coordination improvement run",
        "",
        "Scenario: coord_scale, llm_auction_bidder, scale small_smoke (coord_auction_protocol=round_robin), pipeline_mode=llm_offline.",
        "",
        f"- Episodes: {summary_data['num_episodes']}, base_seed: {args.seed}",
        f"- Results: `results.json`",
        f"- Attribution in results: {summary_data['llm_attribution_present']} (set LABTRUST_LLM_TRACE=1 for attribution).",
        "",
        "Reproduce:",
        "```",
        f"python scripts/run_plan_results_coordination.py --out-dir {out_dir}",
        "```",
    ]
    summary_md_path = out_dir / "plan_results_coordination_summary.md"
    summary_md_path.write_text("\n".join(summary_md_lines), encoding="utf-8")

    print(f"Wrote {results_path}, {summary_json_path}, {summary_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
