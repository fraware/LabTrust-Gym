"""labtrust CLI: validate-policy and future commands."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from labtrust_gym.config import get_repo_root
from labtrust_gym.policy.validate import validate_policy
from labtrust_gym.version import __version__


def _get_partner_id(args: argparse.Namespace) -> str | None:
    """Partner ID from --partner or LABTRUST_PARTNER env."""
    partner = getattr(args, "partner", None)
    if partner is not None and partner != "":
        return partner
    return os.environ.get("LABTRUST_PARTNER") or None


def _git_sha() -> str | None:
    """Return git commit hash or None."""
    try:
        import subprocess

        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=get_repo_root(),
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()[:12]
    except Exception:
        pass
    return None


def main() -> int:
    # Handle --version / -V before subparsers (so "labtrust --version" works)
    if "--version" in sys.argv or "-V" in sys.argv:
        sha = _git_sha()
        if sha:
            print(f"labtrust-gym {__version__} (git {sha})")
        else:
            print(f"labtrust-gym {__version__}")
        return 0

    parser = argparse.ArgumentParser(prog="labtrust", description="LabTrust-Gym CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser(
        "validate-policy",
        help="Validate policy files against schemas (and partner overlay if --partner set)",
    )
    p_validate.add_argument(
        "--partner",
        default=None,
        help="Partner ID for overlay validation (e.g. hsl_like); also LABTRUST_PARTNER env",
    )
    p_validate.set_defaults(func=_run_validate_policy_wrapper)
    p_bench = sub.add_parser(
        "run-benchmark",
        help="Run benchmark task and write results.json",
    )
    p_bench.add_argument(
        "--task", required=True, help="TaskA, TaskB, TaskC, TaskD, TaskE, TaskF"
    )
    p_bench.add_argument("--episodes", type=int, default=10, help="Number of episodes")
    p_bench.add_argument("--seed", type=int, default=123, help="Base seed")
    p_bench.add_argument("--out", default="results.json", help="Output JSON path")
    p_bench.add_argument(
        "--partner",
        default=None,
        help="Partner overlay ID (e.g. hsl_like); also LABTRUST_PARTNER env",
    )
    p_bench.add_argument(
        "--log",
        default=None,
        help="Episode step log path (JSONL); deterministic given seed+actions",
    )
    p_bench.add_argument(
        "--llm-backend",
        choices=["deterministic", "openai_live"],
        default=None,
        help="LLM agent backend: deterministic (seeded, no API) or openai_live (requires OPENAI_API_KEY). Default: no LLM (scripted ops).",
    )
    p_bench.add_argument(
        "--use-llm-live-openai",
        action="store_true",
        help="Use live OpenAI backend (same as --llm-backend openai_live; deprecated in favor of --llm-backend)",
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
    p_study.add_argument(
        "--partner",
        default=None,
        help="Partner overlay ID (e.g. hsl_like); also LABTRUST_PARTNER env",
    )
    p_study.add_argument(
        "--timing",
        choices=["explicit", "simulated"],
        default=None,
        help="Override spec timing_mode: explicit or simulated (default: use spec)",
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
    p_export_receipts = sub.add_parser(
        "export-receipts",
        help="Export Receipt.v0.1 and EvidenceBundle.v0.1 from an episode log (JSONL)",
    )
    p_export_receipts.add_argument(
        "--run",
        required=True,
        help="Episode log path (JSONL, e.g. runs/repro_minimal_xxx/taska/logs/cond_0/episodes.jsonl)",
    )
    p_export_receipts.add_argument(
        "--out",
        required=True,
        help="Output directory (EvidenceBundle.v0.1 written under this dir)",
    )
    p_export_receipts.add_argument(
        "--partner",
        default=None,
        help="Partner overlay ID; when set, include policy_pack_manifest and policy_root_hash",
    )
    p_export_receipts.set_defaults(func=_run_export_receipts)
    p_export_fhir = sub.add_parser(
        "export-fhir",
        help="Export FHIR R4 Bundle from receipts dir (EvidenceBundle.v0.1 or receipt_*.v0.1.json)",
    )
    p_export_fhir.add_argument(
        "--receipts",
        required=True,
        help="Receipts directory (e.g. EvidenceBundle.v0.1 or dir containing receipt_*.v0.1.json)",
    )
    p_export_fhir.add_argument(
        "--out",
        required=True,
        help="Output directory (fhir_bundle.json written here)",
    )
    p_export_fhir.add_argument(
        "--filename",
        default="fhir_bundle.json",
        help="Output filename (default: fhir_bundle.json)",
    )
    p_export_fhir.set_defaults(func=_run_export_fhir)
    p_verify_bundle = sub.add_parser(
        "verify-bundle",
        help="Verify EvidenceBundle.v0.1: manifest integrity, schema, hashchain, invariant trace",
    )
    p_verify_bundle.add_argument(
        "--bundle",
        required=True,
        help="EvidenceBundle.v0.1 directory (e.g. out/EvidenceBundle.v0.1)",
    )
    p_verify_bundle.add_argument(
        "--allow-extra-files",
        action="store_true",
        help="Do not fail on files present but not in manifest (e.g. fhir_bundle.json)",
    )
    p_verify_bundle.set_defaults(func=_run_verify_bundle)
    p_ui_export = sub.add_parser(
        "ui-export",
        help="Export UI-ready bundle (index, events, receipts_index, reason_codes) from a run dir",
    )
    p_ui_export.add_argument(
        "--run",
        required=True,
        help="Run directory: labtrust_runs/quick_eval_* or package-release output",
    )
    p_ui_export.add_argument(
        "--out",
        required=True,
        help="Output path for ui_bundle.zip",
    )
    p_ui_export.set_defaults(func=_run_ui_export)
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
    p_repro.add_argument(
        "--seed-base",
        type=int,
        default=None,
        help="Fixed seed base for determinism (default 100)",
    )
    p_repro.set_defaults(func=_run_reproduce)
    p_package_release = sub.add_parser(
        "package-release",
        help="Release candidate artifact: reproduce + receipts + FHIR + plots + MANIFEST + BENCHMARK_CARD",
    )
    p_package_release.add_argument(
        "--profile",
        required=True,
        choices=["minimal", "full", "paper_v0.1"],
        help="minimal or full reproduce profile; paper_v0.1 = benchmark-first (baselines + TaskF study + summarize + receipts + FIGURES/TABLES)",
    )
    p_package_release.add_argument(
        "--out",
        required=True,
        help="Output directory for the release artifact",
    )
    p_package_release.add_argument(
        "--seed-base",
        type=int,
        default=None,
        help="Fixed seed base for determinism (default 100). When set, timestamps in metadata are deterministic.",
    )
    p_package_release.add_argument(
        "--keep-repro",
        action="store_true",
        help="Keep _repro intermediate directory in output",
    )
    p_package_release.set_defaults(func=_run_package_release)
    p_summarize = sub.add_parser(
        "summarize-results",
        help="Load results.json from dir(s)/file(s), aggregate by task+baseline+partner_id, write summary CSV + markdown",
    )
    p_summarize.add_argument(
        "--in",
        dest="in_paths",
        nargs="+",
        required=True,
        help="Input paths: directories or results.json files",
    )
    p_summarize.add_argument(
        "--out",
        required=True,
        help="Output directory for summary.csv and summary.md",
    )
    p_summarize.add_argument(
        "--basename",
        default="summary",
        help="Output basename (default: summary -> summary.csv, summary.md)",
    )
    p_summarize.set_defaults(func=_run_summarize_results)
    p_gen_baselines = sub.add_parser(
        "generate-official-baselines",
        help="Regenerate and freeze official baseline results (Tasks A–F); write results/, summary.csv, summary.md, metadata.json. Refuse to overwrite unless --force.",
    )
    p_gen_baselines.add_argument(
        "--out",
        required=True,
        help="Output directory (e.g. benchmarks/baselines_official/v0.2/)",
    )
    p_gen_baselines.add_argument(
        "--episodes",
        type=int,
        default=200,
        help="Number of episodes per task (default 200)",
    )
    p_gen_baselines.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Base seed for episodes (default 123)",
    )
    p_gen_baselines.add_argument(
        "--timing",
        choices=["explicit", "simulated"],
        default="explicit",
        help="Timing mode: explicit or simulated (default: explicit)",
    )
    p_gen_baselines.add_argument(
        "--partner",
        default=None,
        help="Partner overlay ID (e.g. hsl_like); also LABTRUST_PARTNER env",
    )
    p_gen_baselines.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output directory if it exists",
    )
    p_gen_baselines.set_defaults(func=_run_generate_official_baselines)
    from labtrust_gym.cli.eval_agent import register_parser as register_eval_agent

    register_eval_agent(sub)
    p_determinism = sub.add_parser(
        "determinism-report",
        help="Run benchmark twice with identical args; produce determinism_report.md and .json; assert v0.2 metrics and episode log hash identical.",
    )
    p_determinism.add_argument(
        "--task",
        required=True,
        help="Task name (e.g. TaskA, TaskB, TaskC, TaskD, TaskE, TaskF)",
    )
    p_determinism.add_argument(
        "--episodes",
        type=int,
        required=True,
        help="Number of episodes (e.g. 2 for CI)",
    )
    p_determinism.add_argument(
        "--seed",
        type=int,
        required=True,
        help="Base seed for episodes",
    )
    p_determinism.add_argument(
        "--out",
        required=True,
        help="Output directory for determinism_report.md and determinism_report.json",
    )
    p_determinism.add_argument(
        "--partner",
        default=None,
        help="Partner overlay ID (e.g. hsl_like); also LABTRUST_PARTNER env",
    )
    p_determinism.add_argument(
        "--timing",
        choices=["explicit", "simulated"],
        default="explicit",
        help="Timing mode: explicit or simulated (default: explicit). Simulated: device service-time sampling seeded only from --seed.",
    )
    p_determinism.set_defaults(func=_run_determinism_report)
    p_quick_eval = sub.add_parser(
        "quick-eval",
        help="Run 1 episode each of TaskA, TaskD, TaskE with scripted baselines; write markdown summary and logs under ./labtrust_runs/",
    )
    p_quick_eval.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed for episodes (default 42)",
    )
    p_quick_eval.add_argument(
        "--timing",
        choices=["explicit", "simulated"],
        default="explicit",
        help="Timing mode: explicit or simulated",
    )
    p_quick_eval.add_argument(
        "--out-dir",
        default="labtrust_runs",
        help="Output directory for run (default: labtrust_runs)",
    )
    p_quick_eval.set_defaults(func=_run_quick_eval)
    p_train_ppo = sub.add_parser(
        "train-ppo",
        help="Train PPO on TaskA (or other task); requires [marl] extra",
    )
    p_train_ppo.add_argument(
        "--task", default="TaskA", help="Task name (default TaskA)"
    )
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
    p_eval_ppo.add_argument(
        "--episodes", type=int, default=50, help="Evaluation episodes"
    )
    p_eval_ppo.add_argument("--seed", type=int, default=123, help="Random seed")
    p_eval_ppo.add_argument("--out", default=None, help="Output JSON path for metrics")
    p_eval_ppo.set_defaults(func=_run_eval_ppo)
    args = parser.parse_args()
    return args.func(args)


def _run_validate_policy_wrapper(args: argparse.Namespace) -> int:
    """Run policy validation (with optional partner)."""
    root = get_repo_root()
    partner_id = _get_partner_id(args)
    return _run_validate_policy(root, partner_id)


def _run_validate_policy(root: Path, partner_id: str | None = None) -> int:
    """Run policy validation; print errors to stderr; return 0 on success, 1 on failure."""
    errors = validate_policy(root, partner_id=partner_id)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("Policy validation OK.", file=sys.stderr)
    if partner_id:
        print(f"Partner overlay {partner_id!r} validated.", file=sys.stderr)
    return 0


def _run_benchmark(args: argparse.Namespace) -> int:
    """Run benchmark and write results.json."""
    from labtrust_gym.benchmarks.runner import run_benchmark as _run

    root = get_repo_root()
    partner_id = _get_partner_id(args)
    llm_backend = getattr(args, "llm_backend", None)
    if getattr(args, "use_llm_live_openai", False):
        llm_backend = "openai_live"
    _run(
        task_name=args.task,
        num_episodes=args.episodes,
        base_seed=args.seed,
        out_path=Path(args.out),
        repo_root=root,
        log_path=Path(args.log) if getattr(args, "log", None) else None,
        partner_id=partner_id,
        llm_backend=llm_backend,
        timing_mode=getattr(args, "timing", None),
    )
    print(f"Wrote {args.out}", file=sys.stderr)
    if getattr(args, "log", None):
        print(f"Episode log {args.log}", file=sys.stderr)
    if partner_id:
        print(f"Partner {partner_id!r}", file=sys.stderr)
    return 0


def _run_make_plots(args: argparse.Namespace) -> int:
    """Generate plots and data tables from study run."""
    from labtrust_gym.studies.plots import make_plots

    root = get_repo_root()
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    make_plots(run_dir)
    print(f"Figures and data tables written to {run_dir / 'figures'}", file=sys.stderr)
    return 0


def _run_export_receipts(args: argparse.Namespace) -> int:
    """Export receipts and evidence bundle from episode log."""
    from labtrust_gym.export.receipts import export_receipts

    root = get_repo_root()
    run_path = Path(args.run)
    if not run_path.is_absolute():
        run_path = root / run_path
    if not run_path.exists():
        print(f"Episode log not found: {run_path}", file=sys.stderr)
        return 1
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    partner_id = _get_partner_id(args)
    policy_root = root if getattr(args, "partner", None) is not None else None
    if policy_root is None and partner_id is not None:
        policy_root = root
    bundle_dir = export_receipts(
        run_path,
        out_dir,
        partner_id=partner_id,
        policy_root=policy_root,
    )
    print(f"Evidence bundle written to {bundle_dir}", file=sys.stderr)
    return 0


def _run_verify_bundle(args: argparse.Namespace) -> int:
    """Verify EvidenceBundle.v0.1: manifest integrity, schema, hashchain, invariant trace."""
    from labtrust_gym.export.verify import verify_bundle

    root = get_repo_root()
    bundle_path = Path(args.bundle)
    if not bundle_path.is_absolute():
        bundle_path = root / bundle_path
    if not bundle_path.is_dir():
        print(f"Bundle not found or not a directory: {bundle_path}", file=sys.stderr)
        return 1
    allow_extra = getattr(args, "allow_extra_files", False)
    passed, report, errors = verify_bundle(
        bundle_path,
        policy_root=root,
        allow_extra_files=allow_extra,
    )
    print(report)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
    return 0 if passed else 1


def _run_ui_export(args: argparse.Namespace) -> int:
    """Export UI-ready zip (index, events, receipts_index, reason_codes) from run dir."""
    from labtrust_gym.export.ui_export import export_ui_bundle

    root = get_repo_root()
    run_path = Path(args.run)
    if not run_path.is_absolute():
        run_path = root / run_path
    if not run_path.is_dir():
        print(f"Run directory not found: {run_path}", file=sys.stderr)
        return 1
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    try:
        export_ui_bundle(run_path, out_path, repo_root=root)
        print(f"UI bundle written to {out_path}", file=sys.stderr)
        return 0
    except (ValueError, FileNotFoundError) as e:
        print(f"ui-export failed: {e}", file=sys.stderr)
        return 1


def _run_export_fhir(args: argparse.Namespace) -> int:
    """Export FHIR R4 Bundle from receipts directory."""
    from labtrust_gym.export.fhir_r4 import export_fhir

    root = get_repo_root()
    receipts_dir = Path(args.receipts)
    if not receipts_dir.is_absolute():
        receipts_dir = root / receipts_dir
    if not receipts_dir.exists():
        print(f"Receipts directory not found: {receipts_dir}", file=sys.stderr)
        return 1
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = getattr(args, "filename", "fhir_bundle.json")
    out_path = export_fhir(receipts_dir, out_dir, out_filename=filename)
    print(f"FHIR bundle written to {out_path}", file=sys.stderr)
    return 0


def _run_reproduce(args: argparse.Namespace) -> int:
    """Run reproduce: minimal study sweep (TaskA, TaskC) + plots."""
    from labtrust_gym.studies.reproduce import main as reproduce_main

    root = get_repo_root()
    out = getattr(args, "out", None)
    out_path = Path(out) if out else None
    if out_path is not None and not out_path.is_absolute():
        out_path = root / out_path
    seed_base = getattr(args, "seed_base", None)
    return reproduce_main(
        profile=args.profile,
        out_dir=out_path,
        repo_root=root,
        seed_base=seed_base,
    )


def _run_package_release(args: argparse.Namespace) -> int:
    """Run package-release: reproduce + export receipts/FHIR + plots + MANIFEST + BENCHMARK_CARD."""
    from labtrust_gym.studies.package_release import run_package_release

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    seed_base = getattr(args, "seed_base", None)
    include_repro = getattr(args, "keep_repro", False)
    try:
        result = run_package_release(
            profile=args.profile,
            out_dir=out_dir,
            repo_root=root,
            seed_base=seed_base,
            include_repro_dir=include_repro,
        )
        print(f"Release artifact written to {result}", file=sys.stderr)
        print(
            f"  MANIFEST.v0.1.json, BENCHMARK_CARD.md, metadata.json", file=sys.stderr
        )
        print(f"  results.json, plots/, tables/, receipts/, fhir/", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"package-release failed: {e}", file=sys.stderr)
        return 1


def _run_study(args: argparse.Namespace) -> int:
    """Run study from spec; write manifest, conditions.jsonl, results/, logs/."""
    from labtrust_gym.studies.study_runner import run_study

    root = get_repo_root()
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    partner_id = _get_partner_id(args)
    run_study(
        spec_path,
        out_dir,
        repo_root=root,
        partner_id=partner_id,
        timing_mode=getattr(args, "timing", None),
    )
    print(f"Study written to {out_dir}", file=sys.stderr)
    return 0


def _run_summarize_results(args: argparse.Namespace) -> int:
    """Load results.json from --in paths, aggregate, write summary.csv + summary.md to --out."""
    from labtrust_gym.benchmarks.summarize import run_summarize

    root = get_repo_root()
    in_paths = [
        root / p if not Path(p).is_absolute() else Path(p) for p in args.in_paths
    ]
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    basename = getattr(args, "basename", "summary")
    csv_path, md_path = run_summarize(in_paths, out_dir, out_basename=basename)
    print(f"Wrote {csv_path}", file=sys.stderr)
    print(f"Wrote {md_path}", file=sys.stderr)
    return 0


def _run_determinism_report(args: argparse.Namespace) -> int:
    """Run benchmark twice in fresh temp dirs; write determinism_report.md and .json; exit 1 if non-deterministic."""
    from labtrust_gym.benchmarks.determinism_report import run_determinism_report

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    partner_id = _get_partner_id(args)
    timing = getattr(args, "timing", "explicit") or "explicit"
    passed, report, _ = run_determinism_report(
        task_name=args.task,
        num_episodes=args.episodes,
        base_seed=args.seed,
        out_dir=out_dir,
        partner_id=partner_id,
        timing_mode=timing,
        repo_root=root,
    )
    print(f"Wrote {out_dir / 'determinism_report.json'}", file=sys.stderr)
    print(f"Wrote {out_dir / 'determinism_report.md'}", file=sys.stderr)
    if passed:
        print("Determinism check PASSED.", file=sys.stderr)
        return 0
    for e in report.get("errors", []):
        print(e, file=sys.stderr)
    return 1


def _run_generate_official_baselines(args: argparse.Namespace) -> int:
    """Regenerate official baseline results: run Tasks A–F (from registry), write results/, summary.csv, summary.md, metadata.json."""
    import json
    from datetime import datetime, timezone, timedelta

    from labtrust_gym.benchmarks.baseline_registry import (
        load_official_baseline_registry,
    )
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.benchmarks.summarize import run_summarize, validate_results_v02

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir

    if out_dir.exists() and not getattr(args, "force", False):
        print(
            f"Refusing to overwrite existing directory: {out_dir}. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    episodes = getattr(args, "episodes", 200)
    seed = getattr(args, "seed", 123)
    timing = getattr(args, "timing", "explicit") or "explicit"
    partner_id = _get_partner_id(args)
    git_sha = _git_sha()

    tasks_in_order, task_to_baseline_id, task_to_suffix = (
        load_official_baseline_registry(root)
    )
    schema_path = root / "policy" / "schemas" / "results.v0.2.schema.json"
    if not schema_path.exists():
        schema_path = None

    policy_fingerprint = None
    try:
        from labtrust_gym.policy.loader import load_effective_policy

        _, policy_fingerprint, _, _ = load_effective_policy(root, partner_id=partner_id)
    except Exception:
        pass

    out_dir.mkdir(parents=True, exist_ok=True)
    results_dir = out_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    for task in tasks_in_order:
        suffix = task_to_suffix.get(
            task, task_to_baseline_id.get(task, "scripted_ops_v1").replace("_v1", "")
        )
        out_path = results_dir / f"{task}_{suffix}.json"
        print(
            f"Running {task} ({episodes} episodes, seed={seed}, timing={timing}) -> {out_path}",
            file=sys.stderr,
        )
        run_benchmark(
            task_name=task,
            num_episodes=episodes,
            base_seed=seed,
            out_path=out_path,
            repo_root=root,
            log_path=None,
            partner_id=partner_id,
            timing_mode=timing,
        )
        if schema_path:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            errors = validate_results_v02(data, schema_path=schema_path)
            if errors:
                for e in errors:
                    print(f"Validation error {out_path}: {e}", file=sys.stderr)
                return 1

    result_paths = [
        results_dir / f"{task}_{task_to_suffix[task]}.json" for task in tasks_in_order
    ]
    csv_path, md_path = run_summarize(
        result_paths,
        out_dir,
        out_basename="summary",
    )
    print(f"Wrote {csv_path}", file=sys.stderr)
    print(f"Wrote {md_path}", file=sys.stderr)

    # Deterministic timestamp when seed provided (UTC epoch + seed seconds)
    if seed is not None:
        ts = (
            datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seed)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    baseline_ids_used = list(
        dict.fromkeys(task_to_baseline_id[t] for t in tasks_in_order)
    )
    metadata = {
        "version": "0.2",
        "description": "Official baseline results (frozen). Regenerate with: labtrust generate-official-baselines --out <dir> --episodes <n> --seed <s>. Use --force to overwrite.",
        "git_sha": git_sha,
        "policy_fingerprint": policy_fingerprint,
        "cli_args": {
            "out": str(out_dir),
            "episodes": episodes,
            "seed": seed,
            "timing": timing,
            "partner": partner_id,
            "force": getattr(args, "force", False),
        },
        "tasks": list(tasks_in_order),
        "baseline_ids": baseline_ids_used,
        "agent_baseline_ids": baseline_ids_used,
        "timestamp": ts,
    }
    metadata_path = out_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Wrote {metadata_path}", file=sys.stderr)
    return 0


def _run_bench_smoke(args: argparse.Namespace) -> int:
    """Run 1 episode per task (TaskA, TaskB, TaskC); exit 0 if all succeed."""
    from labtrust_gym.benchmarks.runner import run_benchmark

    root = get_repo_root()
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


def _run_quick_eval(args: argparse.Namespace) -> int:
    """Run 1 episode each of TaskA, TaskD, TaskE; write markdown summary and logs under labtrust_runs/."""
    import json
    from datetime import datetime

    from labtrust_gym.benchmarks.runner import run_benchmark

    root = get_repo_root()
    seed = getattr(args, "seed", 42)
    out_dir = Path(getattr(args, "out_dir", "labtrust_runs"))
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_dir = out_dir / f"quick_eval_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    tasks = ["TaskA", "TaskD", "TaskE"]
    rows: list[dict] = []
    for task in tasks:
        results_path = run_dir / f"{task}.json"
        log_path = logs_dir / f"{task}.jsonl"
        run_benchmark(
            task_name=task,
            num_episodes=1,
            base_seed=seed,
            out_path=results_path,
            repo_root=root,
            log_path=log_path,
        )
        with open(results_path, encoding="utf-8") as f:
            data = json.load(f)
        ep = (data.get("episodes") or [{}])[0]
        metrics = ep.get("metrics") or {}
        rows.append(
            {
                "task": task,
                "throughput": metrics.get("throughput", 0),
                "violation_count": metrics.get("violation_count", 0),
                "blocked_count": metrics.get("blocked_count", 0),
            }
        )

    # Markdown summary
    lines = [
        "# LabTrust-Gym quick-eval",
        "",
        f"Run: {stamp}",
        f"Seed: {seed}",
        f"Tasks: {', '.join(tasks)}",
        "",
        "| Task | Throughput | Violations | Blocked |",
        "|------|------------|------------|--------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['task']} | {r['throughput']} | {r['violation_count']} | {r['blocked_count']} |"
        )
    lines.extend(["", f"Logs: `{logs_dir}`", ""])
    summary_path = run_dir / "summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"quick-eval written to {run_dir}", file=sys.stderr)
    print(summary_path.read_text(), file=sys.stdout)
    return 0


def _run_train_ppo(args: argparse.Namespace) -> int:
    """Train PPO and save model + eval metrics."""
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    root = get_repo_root()
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

    root = get_repo_root()
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
