#!/usr/bin/env python3
"""
Full pipeline smoke: run coord_risk (or coord_scale) in agent_driven mode over a list of methods.

Collects results metadata (cost, latency) and writes a summary JSON/CSV. Use deterministic
backend for CI; use openai_live with --allow-network for live cost reporting.
When python-dotenv is installed, the script loads .env from the current directory (or
LABTRUST_DOTENV_PATH) so OPENAI_API_KEY is set; run from repo root if .env is there.

Usage:
  python scripts/run_full_pipeline_smoke.py [--backend deterministic] [--out runs/full_pipeline_smoke]
  python scripts/run_full_pipeline_smoke.py --backend openai_live --allow-network --episodes 1 --out runs/live_check
  (Default --methods: all four LLM coord methods for live; use --methods to override.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# All four LLM coord methods; used as default when backend is live so full benchmark runs.
DEFAULT_LLM_METHODS = [
    "llm_central_planner",
    "llm_auction_bidder",
    "llm_central_planner_debate",
    "llm_central_planner_agentic",
]

# Repo root from this script's location (scripts/run_full_pipeline_smoke.py -> parent.parent)
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_FROM_SCRIPT = _SCRIPT_DIR.parent


def _load_dotenv_if_available() -> None:
    """Load .env so OPENAI_API_KEY etc. are set (when python-dotenv is installed).
    Tries repo root .env (from script path), then LABTRUST_DOTENV_PATH, then cwd .env.
    Resolves paths so Windows and any cwd work.
    """
    try:
        from dotenv import load_dotenv

        # 1) Repo root .env (does not depend on cwd)
        env_at_root = _REPO_ROOT_FROM_SCRIPT / ".env"
        if env_at_root.is_file():
            load_dotenv(env_at_root)
        # 2) Explicit path or cwd .env (resolve for Windows and correctness)
        path = os.environ.get("LABTRUST_DOTENV_PATH", "").strip() or ".env"
        resolved = Path(path).resolve()
        if resolved.is_file():
            load_dotenv(resolved)
        elif path == ".env":
            load_dotenv(path)
    except ImportError:
        pass


def _repo_root() -> Path:
    from labtrust_gym.config import get_repo_root

    return Path(get_repo_root())


def main() -> int:
    _load_dotenv_if_available()
    parser = argparse.ArgumentParser(
        description="Run full pipeline smoke (agent_driven + coord_risk) over methods; write cost/latency summary.",
    )
    parser.add_argument(
        "--backend",
        default="deterministic",
        choices=["deterministic", "openai_live", "anthropic_live", "ollama_live"],
        help="LLM backend (default: deterministic for CI).",
    )
    parser.add_argument(
        "--methods",
        default=None,
        help="Comma-separated coordination method IDs (default: all four LLM methods when backend is live, else llm_central_planner_agentic).",
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
        help="Output directory (default: runs/full_pipeline_smoke).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed (default: 42).",
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
    args = parser.parse_args()

    if args.methods is None:
        if args.backend != "deterministic" and args.allow_network:
            args.methods = ",".join(DEFAULT_LLM_METHODS)
        else:
            args.methods = "llm_central_planner_agentic"

    # Fail fast with a clear message if live backend is requested but API key is missing
    # (dotenv was already loaded at start of main(); key may be missing if .env not in cwd or dotenv not installed)
    if args.backend == "openai_live" and args.allow_network:
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            print(
                "Error: OPENAI_API_KEY is not set. For live runs, set it in the environment or add it to .env "
                "in the current directory and run from repo root (pip install python-dotenv to load .env).",
                file=sys.stderr,
            )
            return 1
    if args.backend == "anthropic_live" and args.allow_network:
        if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
            print(
                "Error: ANTHROPIC_API_KEY is not set. For live runs, set it or add to .env and run from repo root.",
                file=sys.stderr,
            )
            return 1

    repo = _repo_root()
    out_dir = Path(args.out or str(repo / "runs" / "full_pipeline_smoke")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark

    scale_config = load_scale_config_by_id(repo, args.scale)
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    if not methods:
        print("No methods specified.", file=sys.stderr)
        return 1

    pipeline_mode = args.pipeline_mode
    if pipeline_mode is None:
        pipeline_mode = "llm_live" if args.backend != "deterministic" and args.allow_network else "deterministic"

    summary_rows: list[dict] = []
    for method_id in methods:
        out_path = out_dir / f"results_{method_id.replace(' ', '_')}.json"
        try:
            results = run_benchmark(
                task_name=args.task,
                num_episodes=args.episodes,
                base_seed=args.seed,
                out_path=out_path,
                repo_root=repo,
                coord_method=method_id,
                agent_driven=True,
                llm_backend=args.backend,
                scale_config_override=scale_config,
                pipeline_mode=pipeline_mode,
                allow_network=args.allow_network if args.allow_network else None,
                injection_id="none",
            )
            meta = results.get("metadata") or {}
            row = {
                "method_id": method_id,
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
                "task": args.task,
                "success": False,
                "error": str(e)[:500],
                "estimated_cost_usd": None,
                "mean_llm_latency_ms": None,
                "llm_error_rate": None,
                "episodes": 0,
            }
        summary_rows.append(row)

    summary_path = out_dir / "full_pipeline_summary.json"
    summary_path.write_text(json.dumps(summary_rows, indent=2, sort_keys=True), encoding="utf-8")
    csv_path = out_dir / "full_pipeline_summary.csv"
    cols = [
        "method_id",
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

    print(f"Summary: {summary_path}")
    print(f"CSV: {csv_path}")
    return 0 if all(r.get("success", False) for r in summary_rows) else 1


if __name__ == "__main__":
    sys.exit(main())
