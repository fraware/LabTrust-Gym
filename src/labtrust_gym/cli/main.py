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
    p_bench.add_argument("--task", required=True, help="TaskA, TaskB, TaskC, TaskD")
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
    p_study = sub.add_parser(
        "run-study",
        help="Run study from spec: expand ablations, run benchmark per condition, write artifact dir",
    )
    p_study.add_argument(
        "--spec",
        required=True,
        help="Study spec YAML path (e.g. policy/studies/study_spec.example.v0.1.yaml)",
    )
    p_study.add_argument(
        "--out",
        required=True,
        help="Output directory (e.g. runs/20250101_120000 or runs/my_study)",
    )
    p_study.set_defaults(func=_run_study)
    p_plots = sub.add_parser(
        "make-plots",
        help="Generate figures and data tables from a study run (out_dir/figures/)",
    )
    p_plots.add_argument(
        "--run",
        required=True,
        help="Study output directory (e.g. runs/<id>)",
    )
    p_plots.set_defaults(func=_run_make_plots)
    p_repro = sub.add_parser(
        "reproduce",
        help="Reproduce minimal results and figures (study sweep + plots)",
    )
    p_repro.add_argument(
        "--profile",
        required=True,
        choices=["minimal", "full"],
        help="minimal: small sweep, few episodes; full: same sweep, more episodes",
    )
    p_repro.add_argument(
        "--out",
        default=None,
        help="Output directory (default: runs/repro_<profile>_<timestamp>)",
    )
    p_repro.set_defaults(func=_run_reproduce)
    p_train_ppo = sub.add_parser(
        "train-ppo",
        help="Train PPO on TaskA (or other task); requires [marl] extra",
    )
    p_train_ppo.add_argument("--task", default="TaskA", help="Task name (default TaskA)")
    p_train_ppo.add_argument(
        "--timesteps",
        type=int,
        default=50000,
        help="Training timesteps (default 50000)",
    )
    p_train_ppo.add_argument("--seed", type=int, default=123, help="Random seed")
    p_train_ppo.add_argument(
        "--out",
        default="runs/ppo",
        help="Output directory for model and eval metrics",
    )
    p_train_ppo.set_defaults(func=_run_train_ppo)
    p_eval_ppo = sub.add_parser(
        "eval-ppo",
        help="Evaluate trained PPO policy; requires [marl] extra",
    )
    p_eval_ppo.add_argument("--model", required=True, help="Path to model.zip")
    p_eval_ppo.add_argument("--task", default="TaskA", help="Task name")
    p_eval_ppo.add_argument("--episodes", type=int, default=50, help="Evaluation episodes")
    p_eval_ppo.add_argument("--seed", type=int, default=123, help="Random seed")
    p_eval_ppo.add_argument("--out", default=None, help="Output JSON path for metrics")
    p_eval_ppo.set_defaults(func=_run_eval_ppo)
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


def _run_make_plots(args: argparse.Namespace) -> int:
    """Generate plots and data tables from study run."""
    from labtrust_gym.studies.plots import make_plots

    root = _find_repo_root()
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    make_plots(run_dir)
    print(f"Figures and data tables written to {run_dir / 'figures'}", file=sys.stderr)
    return 0


def _run_reproduce(args: argparse.Namespace) -> int:
    """Run reproduce: minimal study sweep (TaskA, TaskC) + plots."""
    from labtrust_gym.studies.reproduce import main as reproduce_main

    root = _find_repo_root()
    out = getattr(args, "out", None)
    out_path = Path(out) if out else None
    if out_path is not None and not out_path.is_absolute():
        out_path = root / out_path
    return reproduce_main(
        profile=args.profile,
        out_dir=out_path,
        repo_root=root,
    )


def _run_study(args: argparse.Namespace) -> int:
    """Run study from spec; write manifest, conditions.jsonl, results/, logs/."""
    from labtrust_gym.studies.study_runner import run_study

    root = _find_repo_root()
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    run_study(spec_path, out_dir, repo_root=root)
    print(f"Study written to {out_dir}", file=sys.stderr)
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


def _run_train_ppo(args: argparse.Namespace) -> int:
    """Train PPO and save model + eval metrics."""
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    root = _find_repo_root()
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    result = train_ppo(
        task_name=args.task,
        timesteps=args.timesteps,
        seed=args.seed,
        out_dir=out,
    )
    print(f"Model saved to {result['model_path']}", file=sys.stderr)
    print(f"Eval metrics to {result['eval_metrics_path']}", file=sys.stderr)
    return 0


def _run_eval_ppo(args: argparse.Namespace) -> int:
    """Evaluate trained PPO policy."""
    from labtrust_gym.baselines.marl.ppo_eval import eval_ppo

    root = _find_repo_root()
    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = root / model_path
    out_path = getattr(args, "out", None)
    if out_path and not Path(out_path).is_absolute():
        out_path = root / out_path
    metrics = eval_ppo(
        model_path=str(model_path),
        task_name=args.task,
        episodes=args.episodes,
        seed=args.seed,
        out_path=Path(out_path) if out_path else None,
    )
    print(f"Mean reward: {metrics.get('mean_reward', 0):.2f}", file=sys.stderr)
    if out_path:
        print(f"Metrics written to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
