#!/usr/bin/env python3
"""
Run full LLM coordinator trials with real OpenAI API for the hospital-lab pipeline.

Runs coord_scale with each of the four LLM coord methods (llm_central_planner,
llm_auction_bidder, llm_central_planner_debate, llm_central_planner_agentic)
using pipeline_mode=llm_live, openai_live, allow_network=True. Writes per-run
results and an aggregated trials report (JSON + MD) with duration and
attribution (call_count, latency_ms_sum, cost_usd_sum per backend) when
LABTRUST_LLM_TRACE=1.

Requirements:
  - OPENAI_API_KEY must be set (script exits with clear message if missing).
  - Set LABTRUST_LLM_TRACE=1 to include attribution (or use --trace).

Usage:
  python scripts/run_llm_coord_trials_openai.py [--out-dir DIR] [--episodes 2]
  LABTRUST_LLM_TRACE=1 python scripts/run_llm_coord_trials_openai.py --out-dir ./trials_out
  python scripts/run_llm_coord_trials_openai.py --task coord_risk --injection INJ-BID-SPOOF-001 --methods llm_central_planner

Output:
  <out_dir>/<method_id>_results.json
  <out_dir>/llm_coord_trials_report.json
  <out_dir>/llm_coord_trials_report.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_METHODS = [
    "llm_central_planner",
    "llm_auction_bidder",
    "llm_central_planner_debate",
    "llm_central_planner_agentic",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run LLM coordinator trials with real OpenAI (coord_scale)"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("labtrust_runs/llm_coord_trials_openai"),
        help="Output dir for per-method results and trials report",
    )
    parser.add_argument("--episodes", type=int, default=2, help="Number of episodes per run")
    parser.add_argument("--seed", type=int, default=100, help="Base seed")
    parser.add_argument(
        "--methods",
        type=str,
        default=",".join(DEFAULT_METHODS),
        help="Comma-separated coord method ids (default: all four)",
    )
    parser.add_argument(
        "--scale",
        type=str,
        default="small_smoke",
        help="Scale config id (small_smoke has round_robin for auction)",
    )
    parser.add_argument(
        "--task",
        type=str,
        default="coord_scale",
        choices=("coord_scale", "coord_risk"),
        help="Task: coord_scale (default) or coord_risk",
    )
    parser.add_argument(
        "--injection",
        type=str,
        default=None,
        help="Injection id for coord_risk (e.g. INJ-BID-SPOOF-001); required when --task coord_risk",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Set LABTRUST_LLM_TRACE=1 so attribution is collected",
    )
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print(
            "Error: OPENAI_API_KEY is not set. Set it to run coordinator trials.",
            file=sys.stderr,
        )
        return 1

    if args.trace:
        os.environ["LABTRUST_LLM_TRACE"] = "1"

    method_ids = [m.strip() for m in args.methods.split(",") if m.strip()]
    if not method_ids:
        print("Error: At least one method must be specified (--methods).", file=sys.stderr)
        return 1

    if args.task == "coord_risk" and not (args.injection and args.injection.strip()):
        print(
            "Error: --injection is required when --task coord_risk.",
            file=sys.stderr,
        )
        return 1

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    repo_root = Path(__file__).resolve().parent.parent
    scale_config = load_scale_config_by_id(repo_root, args.scale)

    task_name = args.task
    injection_id = args.injection.strip() if args.injection else None

    report_entries = []
    for method_id in method_ids:
        results_path = out_dir / f"{method_id}_results.json"
        scale_override = scale_config if method_id == "llm_auction_bidder" else scale_config
        results = run_benchmark(
            task_name=task_name,
            num_episodes=args.episodes,
            base_seed=args.seed,
            out_path=results_path,
            repo_root=repo_root,
            coord_method=method_id,
            scale_config_override=scale_override,
            pipeline_mode="llm_live",
            llm_backend="openai_live",
            allow_network=True,
            injection_id=injection_id,
        )
        if not results:
            print(f"Warning: {method_id} run returned no results.", file=sys.stderr)
            entry = {
                "method_id": method_id,
                "task": task_name,
                "num_episodes": args.episodes,
                "pipeline_mode": "llm_live",
                "llm_backend_id": None,
                "run_duration_wall_s": None,
                "by_backend": None,
                "error": "no results",
            }
            if injection_id:
                entry["injection_id"] = injection_id
            report_entries.append(entry)
            continue

        metadata = results.get("metadata") or {}
        att = metadata.get("llm_attribution_summary") or {}
        by_backend = att.get("by_backend")
        if by_backend and isinstance(by_backend, dict):
            by_backend = {
                k: {
                    "call_count": v.get("call_count", 0),
                    "latency_ms_sum": v.get("latency_ms_sum"),
                    "cost_usd_sum": v.get("cost_usd_sum"),
                }
                for k, v in by_backend.items()
                if isinstance(v, dict)
            }
        else:
            by_backend = None

        entry = {
            "method_id": method_id,
            "task": results.get("task", task_name),
            "num_episodes": results.get("num_episodes", args.episodes),
            "pipeline_mode": results.get("pipeline_mode"),
            "llm_backend_id": results.get("llm_backend_id"),
            "run_duration_wall_s": metadata.get("run_duration_wall_s"),
            "by_backend": by_backend,
        }
        if injection_id:
            entry["injection_id"] = injection_id
        report_entries.append(entry)
        print(f"Wrote {results_path}")

    scenario = (
        f"{task_name} LLM coordinator trials (openai_live)"
        + (f", injection={injection_id}" if injection_id else "")
    )
    report_data = {
        "scenario": scenario,
        "task": task_name,
        "scale_id": args.scale,
        "base_seed": args.seed,
        "attribution_present": (
            os.environ.get("LABTRUST_LLM_TRACE", "").strip().lower()
            in ("1", "true", "yes")
        ),
        "methods": report_entries,
    }
    if injection_id:
        report_data["injection_id"] = injection_id

    report_json_path = out_dir / "llm_coord_trials_report.json"
    report_json_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    md_lines = [
        "# LLM coordinator trials report (OpenAI)",
        "",
        "Scenario: {}, pipeline_mode=llm_live, openai_live, scale={}.".format(
            task_name, args.scale
        ),
    ]
    if injection_id:
        md_lines.append("Injection: {}.".format(injection_id))
    md_lines.extend([
        f"Episodes per run: {args.episodes}, base_seed: {args.seed}.",
        "Attribution in report: {} (set LABTRUST_LLM_TRACE=1 for attribution).".format(
            report_data["attribution_present"]
        ),
        "",
        "| method_id | task | num_episodes | pipeline_mode | llm_backend_id | run_duration_wall_s |",
        "|-----------|------|--------------|---------------|----------------|---------------------|",
    ])
    for e in report_entries:
        dur = e.get("run_duration_wall_s")
        dur_s = str(round(dur, 3)) if isinstance(dur, (int, float)) else str(dur)
        md_lines.append(
            "| {} | {} | {} | {} | {} | {} |".format(
                e.get("method_id", ""),
                e.get("task", ""),
                e.get("num_episodes", ""),
                e.get("pipeline_mode", ""),
                e.get("llm_backend_id") or "",
                dur_s,
            )
        )
    md_lines.append("")
    md_lines.append("## by_backend (attribution)")
    md_lines.append("")
    for e in report_entries:
        by_backend = e.get("by_backend")
        md_lines.append(f"### {e.get('method_id', '')}")
        if by_backend:
            for bid, stats in by_backend.items():
                md_lines.append(
                    "- {}: call_count={}, latency_ms_sum={}, cost_usd_sum={}".format(
                        bid,
                        stats.get("call_count"),
                        stats.get("latency_ms_sum"),
                        stats.get("cost_usd_sum"),
                    )
                )
        else:
            md_lines.append("- (no attribution; set LABTRUST_LLM_TRACE=1)")
        md_lines.append("")
    md_lines.append("## Reproduce")
    md_lines.append("")
    md_lines.append("```")
    md_lines.append(
        "LABTRUST_LLM_TRACE=1 python scripts/run_llm_coord_trials_openai.py "
        "--out-dir " + str(out_dir)
    )
    md_lines.append("```")
    report_md_path = out_dir / "llm_coord_trials_report.md"
    report_md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # Write interpretation template (filled numbers, empty Conclusions for human edit)
    interp_lines = [
        "# LLM coordinator trials interpretation",
        "",
        "## Scenario",
        "",
        f"coord_scale, pipeline_mode=llm_live, openai_live, scale={args.scale}, "
        f"episodes per method={args.episodes}, base_seed={args.seed}. "
        f"Attribution collected: {report_data['attribution_present']}.",
        "",
        "## Metrics summary",
        "",
        "| method_id | num_episodes | run_duration_wall_s |",
        "|-----------|--------------|---------------------|",
    ]
    for e in report_entries:
        dur = e.get("run_duration_wall_s")
        dur_s = str(round(dur, 3)) if isinstance(dur, (int, float)) else str(dur)
        interp_lines.append(
            "| {} | {} | {} |".format(
                e.get("method_id", ""),
                e.get("num_episodes", ""),
                dur_s,
            )
        )
    interp_lines.append("")
    if report_data["attribution_present"]:
        interp_lines.append("### by_backend (attribution)")
        interp_lines.append("")
        for e in report_entries:
            by_backend = e.get("by_backend")
            interp_lines.append(f"- **{e.get('method_id', '')}**:")
            if by_backend:
                for bid, stats in by_backend.items():
                    interp_lines.append(
                        "  - {}: call_count={}, latency_ms_sum={}, "
                        "cost_usd_sum={}".format(
                            bid,
                            stats.get("call_count"),
                            stats.get("latency_ms_sum"),
                            stats.get("cost_usd_sum"),
                        )
                    )
            else:
                interp_lines.append("  - (no data)")
            interp_lines.append("")
    interp_lines.append("## Conclusions")
    interp_lines.append("")
    interp_lines.append(
        "(Edit: relative cost/latency across methods, caveats, reproducibility.)"
    )
    interp_lines.append("")
    interp_lines.append("## Artifacts and reproduce")
    interp_lines.append("")
    interp_lines.append(
        f"- `{report_json_path.name}`, `{report_md_path.name}`"
    )
    interp_lines.append("")
    interp_lines.append("```")
    interp_lines.append(
        "LABTRUST_LLM_TRACE=1 python scripts/run_llm_coord_trials_openai.py "
        "--out-dir " + str(out_dir)
    )
    interp_lines.append("```")
    interp_path = out_dir / "llm_coord_trials_interpretation.md"
    interp_path.write_text("\n".join(interp_lines), encoding="utf-8")

    print(f"Wrote {report_json_path}, {report_md_path}, {interp_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
