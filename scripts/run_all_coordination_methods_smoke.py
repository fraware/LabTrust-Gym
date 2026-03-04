#!/usr/bin/env python3
"""
Run coord_risk (and optionally coord_scale) over all coordination methods from the registry.

Loads method IDs from policy/coordination/coordination_methods.v0.1.yaml; supports
--preset full | llm_only | official. Optional --agent-driven runs only agentic-capable
methods (e.g. llm_central_planner_agentic) and collects cost/latency per (method, task).
Writes summary CSV/JSON. Default backend is deterministic (CI-safe); use --llm-backend
and --allow-network for live cost reporting.

Usage:
  python scripts/run_all_coordination_methods_smoke.py [--preset llm_only] [--out runs/all_coord_smoke]
  python scripts/run_all_coordination_methods_smoke.py --agent-driven --llm-backend openai_live --allow-network --out runs/full_pipeline_report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _load_dotenv_if_available() -> None:
    """Load .env from cwd or LABTRUST_DOTENV_PATH so OPENAI_API_KEY etc. are set (when python-dotenv is installed)."""
    try:
        from dotenv import load_dotenv

        path = os.environ.get("LABTRUST_DOTENV_PATH", "").strip() or ".env"
        load_dotenv(path)
    except ImportError:
        pass


def _repo_root() -> Path:
    from labtrust_gym.config import get_repo_root

    return Path(get_repo_root())


# Official pack uses these three coordination methods (minimal set).
OFFICIAL_PACK_METHOD_IDS = ["centralized_planner", "hierarchical_hub_rr", "llm_constrained"]

# Method IDs that support agent_driven (runner uses these with run_episode_agent_driven).
AGENTIC_CAPABLE_METHOD_IDS = ["llm_central_planner_agentic"]


def main() -> int:
    _load_dotenv_if_available()
    parser = argparse.ArgumentParser(
        description="Run coord_risk/coord_scale over all (or preset) coordination methods; write cost/latency summary.",
    )
    parser.add_argument(
        "--preset",
        default="llm_only",
        choices=["full", "llm_only", "official"],
        help="Method set: full=all in registry, llm_only=llm_based only, official=pack's 3 (default: llm_only).",
    )
    parser.add_argument(
        "--task",
        default="coord_risk",
        choices=["coord_risk", "coord_scale"],
        help="Task name (default: coord_risk).",
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=1,
        help="Episodes per method (default: 1).",
    )
    parser.add_argument(
        "--scale",
        default="small_smoke",
        help="Scale config ID (default: small_smoke).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory (default: runs/all_coordination_methods_smoke).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed (default: 42).",
    )
    parser.add_argument(
        "--llm-backend",
        default="deterministic",
        choices=["deterministic", "openai_live", "anthropic_live", "ollama_live", "deterministic_constrained"],
        help="LLM backend (default: deterministic for CI).",
    )
    parser.add_argument(
        "--pipeline-mode",
        default=None,
        help="Override pipeline_mode (e.g. llm_live for live backend).",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network (for live backend).",
    )
    parser.add_argument(
        "--agent-driven",
        action="store_true",
        help="Run in agent_driven mode (only agentic-capable methods; see AGENTIC_CAPABLE_METHOD_IDS).",
    )
    parser.add_argument(
        "--multi-agentic",
        action="store_true",
        help="Use multi_agentic mode when --agent-driven (requires agent_driven).",
    )
    args = parser.parse_args()

    repo = _repo_root()
    out_dir = Path(args.out or str(repo / "runs" / "all_coordination_methods_smoke")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    methods_path = repo / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
    if not methods_path.exists():
        print(f"Registry not found: {methods_path}", file=sys.stderr)
        return 1

    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.policy.coordination import (
        list_llm_coordination_method_ids,
        load_coordination_methods,
    )

    registry = load_coordination_methods(methods_path)
    if args.preset == "full":
        method_ids = sorted(registry.keys())
    elif args.preset == "llm_only":
        method_ids = list_llm_coordination_method_ids(methods_path)
    else:
        method_ids = [m for m in OFFICIAL_PACK_METHOD_IDS if m in registry]
        if not method_ids:
            method_ids = OFFICIAL_PACK_METHOD_IDS

    if args.agent_driven:
        method_ids = [m for m in method_ids if m in AGENTIC_CAPABLE_METHOD_IDS]
        if not method_ids:
            method_ids = list(AGENTIC_CAPABLE_METHOD_IDS)

    if not method_ids:
        print("No methods to run.", file=sys.stderr)
        return 1

    scale_config = load_scale_config_by_id(repo, args.scale)
    pipeline_mode = args.pipeline_mode
    if pipeline_mode is None:
        pipeline_mode = (
            "llm_live"
            if args.llm_backend not in ("deterministic", "deterministic_constrained") and args.allow_network
            else "deterministic"
        )

    summary_rows: list[dict] = []
    for method_id in method_ids:
        out_path = out_dir / f"results_{method_id.replace(' ', '_')}.json"
        try:
            results = run_benchmark(
                task_name=args.task,
                num_episodes=args.episodes,
                base_seed=args.seed,
                out_path=out_path,
                repo_root=repo,
                coord_method=method_id,
                scale_config_override=scale_config,
                pipeline_mode=pipeline_mode,
                llm_backend=args.llm_backend,
                allow_network=args.allow_network if args.allow_network else None,
                injection_id="none",
                agent_driven=args.agent_driven,
                multi_agentic=args.multi_agentic,
            )
            meta = results.get("metadata") or {}
            row = {
                "method_id": method_id,
                "scale_id": args.scale,
                "task": args.task,
                "success": True,
                "estimated_cost_usd": meta.get("estimated_cost_usd"),
                "mean_llm_latency_ms": meta.get("mean_llm_latency_ms"),
                "llm_error_rate": meta.get("llm_error_rate"),
                "episodes": len(results.get("episodes") or []),
            }
        except Exception as e:
            row = {
                "method_id": method_id,
                "scale_id": args.scale,
                "task": args.task,
                "success": False,
                "error": str(e)[:500],
                "estimated_cost_usd": None,
                "mean_llm_latency_ms": None,
                "llm_error_rate": None,
                "episodes": 0,
            }
        summary_rows.append(row)

    summary_path = out_dir / "all_coordination_summary.json"
    summary_path.write_text(json.dumps(summary_rows, indent=2, sort_keys=True), encoding="utf-8")
    csv_path = out_dir / "all_coordination_summary.csv"
    cols = [
        "method_id",
        "scale_id",
        "task",
        "success",
        "estimated_cost_usd",
        "mean_llm_latency_ms",
        "llm_error_rate",
        "episodes",
        "error",
    ]
    with csv_path.open("w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for row in summary_rows:
            f.write(",".join(str(row.get(c, "")) for c in cols) + "\n")

    print(f"Methods: {len(method_ids)}")
    print(f"Summary: {summary_path}")
    print(f"CSV: {csv_path}")
    return 0 if all(r.get("success", False) for r in summary_rows) else 1


if __name__ == "__main__":
    sys.exit(main())
