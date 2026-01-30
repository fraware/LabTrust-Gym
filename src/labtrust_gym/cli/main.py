"""labtrust CLI: validate-policy and future commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from labtrust_gym.policy.validate import validate_policy


def _find_repo_root() -> Path:
    """Assume we run from repo root or from src; walk up to find policy/."""
    cwd = Path.cwd()
    for p in [cwd, cwd.parent]:
        if (p / "policy").is_dir():
            return p
    return cwd


def main() -> int:
    parser = argparse.ArgumentParser(prog="labtrust", description="LabTrust-Gym CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser(
        "validate-policy",
        help="Validate policy files against schemas",
    )
    p_validate.set_defaults(func=lambda _: _run_validate_policy(_find_repo_root()))
    p_bench = sub.add_parser(
        "run-benchmark",
        help="Run benchmark task and write results.json",
    )
    p_bench.add_argument("--task", required=True, help="TaskA, TaskB, TaskC")
    p_bench.add_argument("--episodes", type=int, default=10, help="Number of episodes")
    p_bench.add_argument("--seed", type=int, default=123, help="Base seed")
    p_bench.add_argument("--out", default="results.json", help="Output JSON path")
    p_bench.add_argument(
        "--log",
        default=None,
        help="Episode step log path (JSONL); deterministic given seed+actions",
    )
    p_bench.set_defaults(func=_run_benchmark)
    p_bench_smoke = sub.add_parser(
        "bench-smoke",
        help="Run 1 episode per task (TaskA, TaskB, TaskC); regression smoke.",
    )
    p_bench_smoke.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed for episodes (default 42)",
    )
    p_bench_smoke.set_defaults(func=_run_bench_smoke)
    args = parser.parse_args()
    return args.func(args)


def _run_validate_policy(root: Path) -> int:
    """Run policy validation; print errors to stderr; return 0 on success, 1 on failure."""
    errors = validate_policy(root)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("Policy validation OK.", file=sys.stderr)
    return 0


def _run_benchmark(args: argparse.Namespace) -> int:
    """Run benchmark and write results.json."""
    from labtrust_gym.benchmarks.runner import run_benchmark as _run

    root = _find_repo_root()
    _run(
        task_name=args.task,
        num_episodes=args.episodes,
        base_seed=args.seed,
        out_path=Path(args.out),
        repo_root=root,
        log_path=Path(args.log) if getattr(args, "log", None) else None,
    )
    print(f"Wrote {args.out}", file=sys.stderr)
    if getattr(args, "log", None):
        print(f"Episode log {args.log}", file=sys.stderr)
    return 0


def _run_bench_smoke(args: argparse.Namespace) -> int:
    """Run 1 episode per task (TaskA, TaskB, TaskC); exit 0 if all succeed."""
    from labtrust_gym.benchmarks.runner import run_benchmark

    root = _find_repo_root()
    seed = getattr(args, "seed", 42)
    tasks = ["TaskA", "TaskB", "TaskC"]
    for task in tasks:
        run_benchmark(
            task_name=task,
            num_episodes=1,
            base_seed=seed,
            out_path=root / f"bench_smoke_{task}.json",
            repo_root=root,
        )
        print(f"bench-smoke {task} OK (1 episode, seed={seed})", file=sys.stderr)
    print("bench-smoke all tasks OK.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
