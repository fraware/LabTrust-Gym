"""labtrust CLI: validate-policy and future commands."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC
from pathlib import Path
from typing import Any, cast

from labtrust_gym.config import get_repo_root
from labtrust_gym.policy.validate import validate_policy
from labtrust_gym.version import __version__


def _get_partner_id(args: argparse.Namespace) -> str | None:
    """Partner ID from --partner or LABTRUST_PARTNER env."""
    partner = getattr(args, "partner", None)
    if partner is not None and partner != "":
        return cast(str, partner)
    env_val = os.environ.get("LABTRUST_PARTNER")
    if env_val is None:
        return None
    return env_val


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
        "--task",
        default=None,
        help="TaskA, TaskB, TaskC, TaskD, TaskE, TaskF, TaskG_COORD_SCALE, TaskH_COORD_RISK (omit when using --profile llm_live_eval)",
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
        choices=["deterministic", "openai_live", "openai_responses", "ollama_live"],
        default=None,
        help="LLM agent/coordination backend: deterministic (seeded, no API), openai_live, openai_responses, or ollama_live. Default: no LLM (scripted / deterministic).",
    )
    p_bench.add_argument(
        "--llm-model",
        default=None,
        help="Optional LLM model when using --llm-backend openai_live (e.g. gpt-4o). Overrides LABTRUST_OPENAI_MODEL.",
    )
    p_bench.add_argument(
        "--llm-output-mode",
        choices=["json_schema", "tool_call"],
        default="json_schema",
        help="For openai_responses backend: json_schema (structured output, default) or tool_call (model must call submit_action).",
    )
    p_bench.add_argument(
        "--llm-agents",
        default="ops_0",
        help="Comma-separated agent IDs that use LLM (e.g. ops_0 or ops_0,runner_0). Default: ops_0.",
    )
    p_bench.add_argument(
        "--coord-method",
        default=None,
        help="Coordination method for TaskG_COORD_SCALE / TaskH_COORD_RISK (e.g. centralized_planner, swarm_reactive).",
    )
    p_bench.add_argument(
        "--injection",
        default=None,
        help="Risk injection id for TaskH_COORD_RISK (e.g. INJ-ID-SPOOF-001, INJ-COMMS-POISON-001).",
    )
    p_bench.add_argument(
        "--use-llm-live-openai",
        action="store_true",
        help="Use live OpenAI backend (same as --llm-backend openai_live; deprecated in favor of --llm-backend)",
    )
    p_bench.add_argument(
        "--pipeline-mode",
        choices=["deterministic", "llm_offline", "llm_live"],
        default=None,
        help="Pipeline mode: deterministic (scripted only), llm_offline (LLM with deterministic backend), llm_live (network LLM; requires --allow-network)",
    )
    p_bench.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network for live LLM backends (required for --llm-backend openai_live/ollama_live); also LABTRUST_ALLOW_NETWORK=1",
    )
    p_bench.add_argument(
        "--profile",
        default=None,
        choices=["llm_live_eval"],
        help="Preset: llm_live_eval = TaskD, TaskF, TaskH_COORD_RISK with llm_live + allow-network, writes LLM_TRACE/ (requires --allow-network).",
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
    p_coord_study = sub.add_parser(
        "run-coordination-study",
        help="Run coordination study from spec: (scale x method x injection) matrix, write cells and summary",
    )
    p_coord_study.add_argument(
        "--spec",
        required=True,
        help="Coordination study spec YAML (e.g. policy/coordination/coordination_study_spec.v0.1.yaml)",
    )
    p_coord_study.add_argument(
        "--out",
        required=True,
        help="Output directory (e.g. runs/coord_20250101)",
    )
    p_coord_study.add_argument(
        "--llm-backend",
        choices=["deterministic", "openai_live", "ollama_live"],
        default=None,
        help="Include LLM coordination methods: deterministic, openai_live, or ollama_live. Omit to run only non-LLM methods.",
    )
    p_coord_study.add_argument(
        "--llm-model",
        default=None,
        help="Optional LLM model when using --llm-backend openai_live (e.g. gpt-4o).",
    )
    p_coord_study.set_defaults(func=_run_coordination_study)
    p_coord_security_pack = sub.add_parser(
        "run-coordination-security-pack",
        help="Run internal coordination security regression pack: fixed scale x method x injection matrix, deterministic, 1 ep/cell. Writes pack_results/, pack_summary.csv, pack_gate.md.",
    )
    p_coord_security_pack.add_argument(
        "--out",
        required=True,
        help="Output directory (e.g. runs/coord_security_pack)",
    )
    p_coord_security_pack.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed for deterministic runs (default: 42).",
    )
    p_coord_security_pack.set_defaults(func=_run_coordination_security_pack)
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
    p_risk_bundle = sub.add_parser(
        "build-risk-register-bundle",
        help="Build RiskRegisterBundle.v0.1 JSON (risk register + evidence links) from policy and optional run dirs",
    )
    p_risk_bundle.add_argument(
        "--out",
        required=True,
        help="Output path for risk_register_bundle.v0.1.json",
    )
    p_risk_bundle.add_argument(
        "--run",
        action="append",
        default=[],
        dest="run_dirs",
        help="Run directory(ies) containing SECURITY/, summary/, PARETO/ (can be repeated)",
    )
    p_risk_bundle.add_argument(
        "--include-generated-at",
        action="store_true",
        help="Include generated_at timestamp (omitting keeps bundle fully deterministic)",
    )
    p_risk_bundle.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip schema validation before writing",
    )
    p_risk_bundle.set_defaults(func=_run_build_risk_register_bundle)
    p_export_risk = sub.add_parser(
        "export-risk-register",
        help="Export RiskRegisterBundle.v0.1 into a directory (and optionally inject into run dirs for UI)",
    )
    p_export_risk.add_argument(
        "--out",
        required=True,
        help="Output directory; bundle written as <out>/RISK_REGISTER_BUNDLE.v0.1.json",
    )
    p_export_risk.add_argument(
        "--runs",
        action="append",
        default=[],
        dest="run_specs",
        metavar="DIR_OR_GLOB",
        help="Run directory or glob (e.g. ui_fixtures, labtrust_runs/*); can be repeated",
    )
    p_export_risk.add_argument(
        "--include-official-pack",
        default=None,
        metavar="DIR",
        help="Add this directory (e.g. output of run-official-pack) to evidence run dirs",
    )
    p_export_risk.add_argument(
        "--inject-ui-export",
        action="store_true",
        help="Also write the bundle into each run dir so the UI can load it from there",
    )
    p_export_risk.add_argument(
        "--include-generated-at",
        action="store_true",
        help="Include generated_at timestamp (omitting keeps bundle deterministic)",
    )
    p_export_risk.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip schema validation before writing",
    )
    p_export_risk.set_defaults(func=_run_export_risk_register)
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
    p_package_release.add_argument(
        "--pipeline-mode",
        choices=["deterministic", "llm_offline", "llm_live"],
        default="deterministic",
        help="Pipeline mode (default: deterministic); CI uses deterministic",
    )
    p_package_release.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network (only with --pipeline-mode llm_live); default: disabled",
    )
    p_package_release.set_defaults(func=_run_package_release)
    p_security_suite = sub.add_parser(
        "run-security-suite",
        help="Run security attack suite (smoke or full) and emit SECURITY/attack_results.json + securitization packet",
    )
    p_security_suite.add_argument(
        "--out",
        default="runs/security_suite",
        help="Output directory; SECURITY/ will be created under it (default: runs/security_suite)",
    )
    p_security_suite.add_argument(
        "--smoke",
        action="store_true",
        default=True,
        help="Run only smoke attacks (default True)",
    )
    p_security_suite.add_argument(
        "--full",
        action="store_true",
        help="Run all attacks (overrides --smoke)",
    )
    p_security_suite.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed for deterministic runs (default 42)",
    )
    p_security_suite.set_defaults(func=_run_security_suite)
    p_safety_case = sub.add_parser(
        "safety-case",
        help="Generate safety case (claim→control→test→artifact→command) to SAFETY_CASE/safety_case.json and .md",
    )
    p_safety_case.add_argument(
        "--out",
        required=True,
        help="Output directory; SAFETY_CASE/ will be created under it",
    )
    p_safety_case.set_defaults(func=_run_safety_case)
    p_deps_inventory = sub.add_parser(
        "deps-inventory",
        help="Write runtime dependency inventory (SBOM-lite) to <out>/SECURITY/deps_inventory_runtime.json",
    )
    p_deps_inventory.add_argument(
        "--out",
        required=True,
        help="Output directory; SECURITY/deps_inventory_runtime.json will be created under it",
    )
    p_deps_inventory.set_defaults(func=_run_deps_inventory)
    p_transparency_log = sub.add_parser(
        "transparency-log",
        help="Build global transparency log (TRANSPARENCY_LOG/) over episode digests with Merkle proofs.",
    )
    p_transparency_log.add_argument(
        "--in",
        dest="in_dir",
        required=True,
        help="Input artifact directory (must contain _repr/<task>/ and receipts/<task>/EvidenceBundle.v0.1)",
    )
    p_transparency_log.add_argument(
        "--out",
        required=True,
        help="Output directory; TRANSPARENCY_LOG/ will be created under it",
    )
    p_transparency_log.set_defaults(func=_run_transparency_log)
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
    p_official_pack = sub.add_parser(
        "run-official-pack",
        help="Run official benchmark pack (baselines, SECURITY, SAFETY_CASE, TRANSPARENCY_LOG); single folder ready to upload.",
    )
    p_official_pack.add_argument(
        "--out",
        required=True,
        help="Output directory (official pack result folder)",
    )
    p_official_pack.add_argument(
        "--seed-base",
        type=int,
        default=100,
        help="Base seed for deterministic runs (default 100)",
    )
    p_official_pack.add_argument(
        "--smoke",
        action="store_true",
        default=None,
        help="Use smoke settings (fewer episodes, security smoke-only); default when LABTRUST_OFFICIAL_PACK_SMOKE=1",
    )
    p_official_pack.add_argument(
        "--no-smoke",
        action="store_true",
        help="Disable smoke; run full pack",
    )
    p_official_pack.add_argument(
        "--full",
        action="store_true",
        help="Run full security suite (default: smoke-only)",
    )
    p_official_pack.add_argument(
        "--pipeline-mode",
        choices=["deterministic", "llm_offline", "llm_live"],
        default="deterministic",
        help="Pipeline mode (default: deterministic); CI uses deterministic",
    )
    p_official_pack.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network (only with --pipeline-mode llm_live); default: disabled",
    )
    p_official_pack.set_defaults(func=_run_official_pack)
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
    p_determinism.add_argument(
        "--coord-method",
        default=None,
        help="Coordination method for TaskG_COORD_SCALE / TaskH_COORD_RISK (e.g. kernel_centralized_edf). Defaults to kernel_centralized_edf when task is TaskG or TaskH.",
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
    p_quick_eval.add_argument(
        "--pipeline-mode",
        choices=["deterministic", "llm_offline", "llm_live"],
        default="deterministic",
        help="Pipeline mode (default: deterministic); llm_live requires --allow-network",
    )
    p_quick_eval.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network for live LLM (only with --pipeline-mode llm_live); also LABTRUST_ALLOW_NETWORK=1",
    )
    p_quick_eval.set_defaults(func=_run_quick_eval)
    p_llm_health = sub.add_parser(
        "llm-healthcheck",
        help="One minimal request to live LLM backend; print ok, model_id, latency, usage. Requires --allow-network.",
    )
    p_llm_health.add_argument(
        "--backend",
        choices=["openai_live", "openai_responses"],
        default="openai_responses",
        help="Backend to check (default: openai_responses). openai_live uses legacy Chat Completions; openai_responses uses Responses API with strict schema.",
    )
    p_llm_health.add_argument(
        "--model",
        default=None,
        help="Model override (e.g. gpt-4o-mini). Default from LABTRUST_OPENAI_MODEL.",
    )
    p_llm_health.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network (required for live check); also LABTRUST_ALLOW_NETWORK=1",
    )
    p_llm_health.set_defaults(func=_run_llm_healthcheck)
    p_serve = sub.add_parser(
        "serve",
        help="Start online HTTP API (local-only by default; rate limits and optional API key).",
    )
    p_serve.add_argument(
        "--host",
        default=None,
        help="Bind address (default: 127.0.0.1; use LABTRUST_SERVE_HOST for env override)",
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port (default: 8765; use LABTRUST_SERVE_PORT for env override)",
    )
    p_serve.set_defaults(func=_run_serve)
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
    return cast(int, args.func(args))


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


def _allow_network_from_env() -> bool:
    """True if LABTRUST_ALLOW_NETWORK is 1, true, or yes."""
    v = (os.environ.get("LABTRUST_ALLOW_NETWORK") or "").strip().lower()
    return v in ("1", "true", "yes")


def _run_benchmark(args: argparse.Namespace) -> int:
    """Run benchmark and write results.json."""
    profile = getattr(args, "profile", None)
    if profile == "llm_live_eval":
        return _run_benchmark_llm_live_eval(args)

    if not getattr(args, "task", None):
        print(
            "run-benchmark requires --task (or use --profile llm_live_eval).",
            file=sys.stderr,
        )
        return 1

    from labtrust_gym.benchmarks.runner import run_benchmark as _run

    root = get_repo_root()
    partner_id = _get_partner_id(args)
    llm_backend = getattr(args, "llm_backend", None)
    if getattr(args, "use_llm_live_openai", False):
        llm_backend = "openai_live"
    if llm_backend == "openai_live" and not os.environ.get("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is required for --llm-backend openai_live. Reason code: OPENAI_API_KEY_MISSING",
            file=sys.stderr,
        )
        return 1
    llm_agents_str = getattr(args, "llm_agents", "ops_0") or "ops_0"
    llm_agents = [a.strip() for a in llm_agents_str.split(",") if a.strip()]
    pipeline_mode = getattr(args, "pipeline_mode", None)
    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()
    _run(
        task_name=args.task,
        num_episodes=args.episodes,
        base_seed=args.seed,
        out_path=Path(args.out),
        repo_root=root,
        log_path=Path(args.log) if getattr(args, "log", None) else None,
        partner_id=partner_id,
        llm_backend=llm_backend,
        llm_agents=llm_agents,
        llm_output_mode=getattr(args, "llm_output_mode", "json_schema"),
        llm_model=getattr(args, "llm_model", None),
        timing_mode=getattr(args, "timing", None),
        coord_method=getattr(args, "coord_method", None),
        injection_id=getattr(args, "injection", None),
        pipeline_mode=pipeline_mode,
        allow_network=allow_network,
    )
    print(f"Wrote {args.out}", file=sys.stderr)
    if getattr(args, "log", None):
        print(f"Episode log {args.log}", file=sys.stderr)
    if partner_id:
        print(f"Partner {partner_id!r}", file=sys.stderr)
    return 0


def _run_benchmark_llm_live_eval(args: argparse.Namespace) -> int:
    """Run llm_live_eval profile: TaskD, TaskF, TaskH_COORD_RISK with llm_live, allow-network, LLM_TRACE bundle."""
    from labtrust_gym.benchmarks.llm_trace import LLMTraceCollector
    from labtrust_gym.benchmarks.runner import run_benchmark

    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()
    if not allow_network:
        print(
            "llm_live_eval profile requires --allow-network (or LABTRUST_ALLOW_NETWORK=1). Refusing to run.",
            file=sys.stderr,
        )
        return 1

    root = get_repo_root()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.mkdir(parents=True, exist_ok=True)

    llm_backend = getattr(args, "llm_backend", None) or "openai_responses"
    if llm_backend not in ("openai_live", "openai_responses"):
        llm_backend = "openai_responses"
    llm_agents_str = getattr(args, "llm_agents", "ops_0") or "ops_0"
    llm_agents = [a.strip() for a in llm_agents_str.split(",") if a.strip()]
    num_episodes = getattr(args, "episodes", 2)
    base_seed = getattr(args, "seed", 42)
    partner_id = _get_partner_id(args)

    tasks_config: list[tuple[str, str | None]] = [
        ("TaskD", None),
        ("TaskF", None),
        ("TaskH_COORD_RISK", "kernel_centralized_edf"),
    ]
    collector = LLMTraceCollector()

    for task_name, coord_method in tasks_config:
        task_out = out_path / f"{task_name}.json"
        log_path = out_path / "logs" / f"{task_name}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        run_benchmark(
            task_name=task_name,
            num_episodes=num_episodes,
            base_seed=base_seed,
            out_path=task_out,
            repo_root=root,
            log_path=log_path,
            partner_id=partner_id,
            llm_backend=llm_backend,
            llm_agents=llm_agents,
            pipeline_mode="llm_live",
            allow_network=True,
            coord_method=coord_method,
            llm_trace_collector=collector,
        )
        print(f"Wrote {task_out}", file=sys.stderr)

    trace_dir = out_path / "LLM_TRACE"
    collector.write_to_dir(trace_dir)
    print(f"LLM trace written to {trace_dir}", file=sys.stderr)

    metadata = {
        "profile": "llm_live_eval",
        "pipeline_mode": "llm_live",
        "llm_backend_id": llm_backend,
        "allow_network": True,
        "non_deterministic": True,
        "tasks": [t[0] for t in tasks_config],
        "num_episodes": num_episodes,
        "base_seed": base_seed,
    }
    (out_path / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(
        f"Metadata (non_deterministic=true) written to {out_path / 'metadata.json'}",
        file=sys.stderr,
    )
    return 0


def _run_make_plots(args: argparse.Namespace) -> int:
    """Generate plots and data tables from study run."""
    from labtrust_gym.studies.plots import make_plots

    root = get_repo_root()
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    make_plots(run_dir)
    fig_dir = run_dir / "figures"
    print(f"Figures and data tables written to {fig_dir}", file=sys.stderr)
    print(
        f"  Read {fig_dir / 'RUN_REPORT.md'} for metric definitions and data summary.",
        file=sys.stderr,
    )
    print(
        f"  Read {run_dir / 'RUN_SUMMARY.md'} for run context and output layout.",
        file=sys.stderr,
    )
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


def _run_build_risk_register_bundle(args: argparse.Namespace) -> int:
    """Build RiskRegisterBundle.v0.1 from policy and optional run dirs."""
    from labtrust_gym.export.risk_register_bundle import write_risk_register_bundle

    root = get_repo_root()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    run_dirs = [Path(r) if Path(r).is_absolute() else root / r for r in (args.run_dirs or [])]
    try:
        write_risk_register_bundle(
            repo_root=root,
            out_path=out_path,
            run_dirs=run_dirs,
            include_generated_at=getattr(args, "include_generated_at", False),
            include_git_hash=True,
            validate=not getattr(args, "no_validate", False),
        )
        print(f"Risk register bundle written to {out_path}", file=sys.stderr)
        return 0
    except (ValueError, FileNotFoundError) as e:
        print(f"build-risk-register-bundle failed: {e}", file=sys.stderr)
        return 1


def _run_export_risk_register(args: argparse.Namespace) -> int:
    """Export RiskRegisterBundle.v0.1 into --out dir; optional --runs and --include-official-pack."""
    from labtrust_gym.export.risk_register_bundle import (
        RISK_REGISTER_BUNDLE_FILENAME,
        export_risk_register,
    )

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    run_specs = getattr(args, "run_specs", None) or []
    include_official_pack = getattr(args, "include_official_pack", None)
    if include_official_pack is not None:
        include_official_pack = Path(include_official_pack)
        if not include_official_pack.is_absolute():
            include_official_pack = root / include_official_pack
    try:
        out_path = export_risk_register(
            repo_root=root,
            out_dir=out_dir,
            run_specs=run_specs,
            include_official_pack_dir=include_official_pack,
            include_generated_at=getattr(args, "include_generated_at", False),
            include_git_hash=True,
            validate=not getattr(args, "no_validate", False),
            inject_ui_export=getattr(args, "inject_ui_export", False),
        )
        print(f"{RISK_REGISTER_BUNDLE_FILENAME} written to {out_path}", file=sys.stderr)
        return 0
    except (ValueError, FileNotFoundError) as e:
        print(f"export-risk-register failed: {e}", file=sys.stderr)
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
    pipeline_mode = getattr(args, "pipeline_mode", "deterministic") or "deterministic"
    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()
    try:
        result = run_package_release(
            profile=args.profile,
            out_dir=out_dir,
            repo_root=root,
            seed_base=seed_base,
            include_repro_dir=include_repro,
            pipeline_mode=pipeline_mode,
            allow_network=allow_network,
        )
        print(f"Release artifact written to {result}", file=sys.stderr)
        print("  MANIFEST.v0.1.json, BENCHMARK_CARD.md, metadata.json", file=sys.stderr)
        print("  results.json, plots/, tables/, receipts/, fhir/", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"package-release failed: {e}", file=sys.stderr)
        return 1


def _run_security_suite(args: argparse.Namespace) -> int:
    """Run security attack suite and emit SECURITY/attack_results.json + packet."""
    from labtrust_gym.benchmarks.securitization import emit_securitization_packet
    from labtrust_gym.benchmarks.security_runner import run_suite_and_emit

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    smoke_only = not getattr(args, "full", False)
    seed = getattr(args, "seed", 42)
    try:
        results = run_suite_and_emit(
            policy_root=root,
            out_dir=out_dir,
            repo_root=root,
            smoke_only=smoke_only,
            seed=seed,
            metadata={
                "seed": seed,
                "smoke_only": smoke_only,
                "git_sha": _git_sha(),
            },
        )
        emit_securitization_packet(root, out_dir)
        passed = sum(1 for r in results if r.get("passed"))
        print(
            f"Security suite: {passed}/{len(results)} passed",
            file=sys.stderr,
        )
        print(f"SECURITY/ written to {out_dir / 'SECURITY'}", file=sys.stderr)
        if passed == 0 and results:
            errors = [r.get("error") or "" for r in results]
            need_env = any("pettingzoo or gymnasium" in e for e in errors)
            need_pytest = any("No module named pytest" in e for e in errors)
            if need_env or need_pytest:
                pkgs = []
                if need_env:
                    pkgs.extend(["pettingzoo", "gymnasium"])
                if need_pytest:
                    pkgs.append("pytest")
                exe = sys.executable
                # PowerShell requires & to invoke a quoted path; Cmd does not
                ps_cmd = f'& "{exe}" -m pip install {" ".join(pkgs)}'
                print(
                    "Hint: install into the same Python that runs labtrust (copy-paste):",
                    file=sys.stderr,
                )
                print(f"  {ps_cmd}", file=sys.stderr)
                print(
                    "  (PowerShell: use as-is. Cmd: omit the leading & )",
                    file=sys.stderr,
                )
                ensurepip_cmd = f'& "{exe}" -m ensurepip --upgrade'
                print(
                    f"  (If 'No module named pip', run first: {ensurepip_cmd})",
                    file=sys.stderr,
                )
        return 0 if passed == len(results) else 1
    except Exception as e:
        print(f"run-security-suite failed: {e}", file=sys.stderr)
        return 1


def _run_safety_case(args: argparse.Namespace) -> int:
    """Generate safety case to SAFETY_CASE/safety_case.json and safety_case.md."""
    from labtrust_gym.security.safety_case import emit_safety_case

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        emit_safety_case(policy_root=root, out_dir=out_dir)
        safety_dir = out_dir / "SAFETY_CASE"
        print(f"SAFETY_CASE/ written to {safety_dir}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"safety-case failed: {e}", file=sys.stderr)
        return 1


def _run_deps_inventory(args: argparse.Namespace) -> int:
    """Write runtime dependency inventory to <out>/SECURITY/deps_inventory_runtime.json."""
    from labtrust_gym.security.deps_inventory import write_deps_inventory_runtime

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = write_deps_inventory_runtime(out_dir, repo_root=root)
    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


def _run_transparency_log(args: argparse.Namespace) -> int:
    """Build TRANSPARENCY_LOG/ from artifact dir (--in) into --out."""
    from labtrust_gym.security.transparency import write_transparency_log

    root = get_repo_root()
    in_dir = Path(getattr(args, "in_dir", ""))
    if not in_dir.is_absolute():
        in_dir = root / in_dir
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    if not in_dir.is_dir():
        print(f"Input directory not found: {in_dir}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = write_transparency_log(in_dir, out_dir)
    print(f"Wrote {log_dir} (log.json, root.txt, proofs/)", file=sys.stderr)
    return 0


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


def _run_coordination_study(args: argparse.Namespace) -> int:
    """Run coordination study from spec; write cells/, summary/summary_coord.csv, summary/pareto.md."""
    from labtrust_gym.studies.coordination_study_runner import run_coordination_study

    root = get_repo_root()
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    llm_backend = getattr(args, "llm_backend", None)
    llm_model = getattr(args, "llm_model", None)
    if llm_backend == "openai_live" and not os.environ.get("OPENAI_API_KEY"):
        print(
            "OPENAI_API_KEY is required for --llm-backend openai_live. Reason code: OPENAI_API_KEY_MISSING",
            file=sys.stderr,
        )
        return 1
    run_coordination_study(
        spec_path, out_dir, repo_root=root, llm_backend=llm_backend, llm_model=llm_model
    )
    print(f"Coordination study written to {out_dir}", file=sys.stderr)
    return 0


def _run_coordination_security_pack(args: argparse.Namespace) -> int:
    """Run coordination security pack; write pack_results/, pack_summary.csv, pack_gate.md."""
    from labtrust_gym.studies.coordination_security_pack import run_coordination_security_pack

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    seed_base = getattr(args, "seed", 42)
    run_coordination_security_pack(out_dir=out_dir, repo_root=root, seed_base=seed_base)
    print(f"Coordination security pack written to {out_dir}", file=sys.stderr)
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
        coord_method=getattr(args, "coord_method", None),
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
    from datetime import datetime, timedelta

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
    _schema_candidate = root / "policy" / "schemas" / "results.v0.2.schema.json"
    schema_path: Path | None = _schema_candidate if _schema_candidate.exists() else None

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
        ts = (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=seed)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    else:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

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


def _run_official_pack(args: argparse.Namespace) -> int:
    """Run official benchmark pack: baselines, SECURITY, SAFETY_CASE, TRANSPARENCY_LOG."""
    from labtrust_gym.benchmarks.official_pack import run_official_pack

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    seed_base = getattr(args, "seed_base", 100)
    full_security = getattr(args, "full", False)
    pipeline_mode = getattr(args, "pipeline_mode", "deterministic") or "deterministic"
    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()
    smoke = False
    if getattr(args, "no_smoke", False):
        smoke = False
    elif getattr(args, "smoke", None) is True:
        smoke = True
    else:
        smoke = os.environ.get("LABTRUST_OFFICIAL_PACK_SMOKE", "").strip() in (
            "1",
            "true",
            "yes",
        ) or os.environ.get("LABTRUST_PAPER_SMOKE", "").strip() in ("1", "true", "yes")
    try:
        result = run_official_pack(
            out_dir=out_dir,
            repo_root=root,
            seed_base=seed_base,
            smoke=smoke,
            full_security=full_security,
            pipeline_mode=pipeline_mode,
            allow_network=allow_network,
        )
        print(f"Official pack written to {result}", file=sys.stderr)
        return 0
    except Exception as e:
        import traceback

        print(f"run-official-pack failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


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


def _run_llm_healthcheck(args: argparse.Namespace) -> int:
    """Run one minimal request to live LLM backend; print ok, model_id, latency, usage."""
    from labtrust_gym.pipeline import set_pipeline_config

    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()
    if not allow_network:
        print(
            "llm-healthcheck requires network. Pass --allow-network or set LABTRUST_ALLOW_NETWORK=1.",
            file=sys.stderr,
        )
        return 1
    set_pipeline_config(
        pipeline_mode="llm_live",
        allow_network=True,
        llm_backend_id=getattr(args, "backend", "openai_responses"),
    )
    backend_name = getattr(args, "backend", "openai_responses")
    model_override = getattr(args, "model", None)
    if backend_name == "openai_responses":
        from labtrust_gym.baselines.llm.backends.openai_responses import (
            OpenAILiveResponsesBackend,
        )

        backend = OpenAILiveResponsesBackend(model=model_override)
    else:
        from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend

        backend = OpenAILiveBackend(model=model_override)
    result = backend.healthcheck()
    ok = result.get("ok", False)
    print(f"ok: {ok}", file=sys.stderr)
    print(f"model_id: {result.get('model_id', 'n/a')}", file=sys.stderr)
    print(f"latency_ms: {result.get('latency_ms')}", file=sys.stderr)
    usage = result.get("usage") or {}
    if usage:
        print(f"usage: {usage}", file=sys.stderr)
    if result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
    return 0 if ok else 1


def _run_serve(args: argparse.Namespace) -> int:
    """Start online HTTP server with abuse controls (B004)."""
    from labtrust_gym.online.config import load_online_config
    from labtrust_gym.online.server import run_server

    config = load_online_config()
    host = getattr(args, "host", None) or config.host
    port = getattr(args, "port", None)
    if port is not None:
        port = port % 65536
    else:
        port = config.port
    if host != config.host or port != config.port:
        config = type(config)(
            api_key=config.api_key,
            rate_limit_rps_per_key=config.rate_limit_rps_per_key,
            rate_limit_rps_per_ip=config.rate_limit_rps_per_ip,
            max_body_bytes=config.max_body_bytes,
            max_inflight=config.max_inflight,
            host=host,
            port=port,
            auth_mode=config.auth_mode,
            key_registry=config.key_registry,
        )
    print(
        f"Serving at http://{config.host}:{config.port} (auth_required={config.auth_required})",
        file=sys.stderr,
    )
    run_server(config)
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

    pipeline_mode = getattr(args, "pipeline_mode", "deterministic") or "deterministic"
    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()

    tasks = ["TaskA", "TaskD", "TaskE"]
    rows: list[dict[str, Any]] = []
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
            pipeline_mode=pipeline_mode,
            allow_network=allow_network,
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
