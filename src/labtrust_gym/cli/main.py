"""
LabTrust-Gym command-line interface.

Entry point for all labtrust commands: validate-policy, run-benchmark,
quick-eval, package-release, export-risk-register, and many others. Subcommands
and options are registered via add_subparsers; each command has a handler that
returns an exit code. Use --profile to load a lab profile; use --partner or
LABTRUST_PARTNER for partner overlay validation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from labtrust_gym.cli.console import (
    CLIOutput,
    Verbosity,
    get_console,
    set_console,
    verbosity_from_args,
)
from labtrust_gym.cli.logging_config import configure_cli_logging
from labtrust_gym.config import get_repo_root, load_lab_profile
from labtrust_gym.plugins import load_plugins
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
    # Load .env so OPENAI_API_KEY / ANTHROPIC_API_KEY are available for live LLM runs
    try:
        from dotenv import load_dotenv

        path = os.environ.get("LABTRUST_DOTENV_PATH", "").strip() or ".env"
        load_dotenv(path)
        # Always try repo root .env (absolute path) so keys work regardless of cwd
        try:
            root = Path(get_repo_root())
            env_at_root = root / ".env"
            if env_at_root.is_file():
                load_dotenv(env_at_root)
        except Exception:
            pass
    except ImportError:
        pass

    # Handle --version / -V before subparsers (so "labtrust --version" works)
    if "--version" in sys.argv or "-V" in sys.argv:
        sha = _git_sha()
        if sha:
            print(f"labtrust-gym {__version__} (git {sha})")
        else:
            print(f"labtrust-gym {__version__}")
        return 0

    load_plugins()

    parser = argparse.ArgumentParser(prog="labtrust", description="LabTrust-Gym CLI")
    parser.add_argument(
        "--profile",
        default=None,
        metavar="ID",
        help="Lab profile ID (loads policy/lab_profiles/<id>.v0.1.yaml); overrides partner_id and optional paths when set",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output (debug logs, progress detail, tracebacks).",
    )
    parser.add_argument(
        "-q",
        "--global-quiet",
        dest="global_quiet",
        action="store_true",
        help="Minimal output (errors and summary only).",
    )
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
    p_validate.add_argument(
        "--strict-tool-provenance",
        action="store_true",
        help="Also validate tool registry SBOM/attestation: require_sbom and ref existence when set.",
    )
    p_validate.add_argument(
        "--domain",
        default=None,
        help="Domain ID for policy/domains/<domain_id>/; load and validate domain-merged policy.",
    )
    p_validate.set_defaults(func=_run_validate_policy_wrapper)
    p_bench = sub.add_parser(
        "run-benchmark",
        help="Run benchmark task and write results.json",
    )
    p_bench.add_argument(
        "--task",
        default=None,
        help="throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk (omit when using --profile llm_live_eval)",
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
        choices=[
            "deterministic",
            "deterministic_constrained",
            "deterministic_policy_v1",
            "openai_live",
            "openai_hosted",
            "openai_responses",
            "ollama_live",
            "anthropic_live",
        ],
        default=None,
        help="LLM backend: deterministic (fixtures), deterministic_constrained (seeded RNG), deterministic_policy_v1 (preference-order policy, optional), openai_live, openai_responses, ollama_live, anthropic_live.",
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
        help="Coordination method for coord_scale / coord_risk (e.g. centralized_planner, swarm_reactive).",
    )
    p_bench.add_argument(
        "--injection",
        default=None,
        help="Risk injection id for coord_risk (e.g. INJ-ID-SPOOF-001, INJ-COMMS-POISON-001).",
    )
    p_bench.add_argument(
        "--scale",
        default=None,
        help="Scale config id for coord_scale / coord_risk (e.g. small_smoke, medium_stress_signed_bus, corridor_heavy). Uses task default if omitted.",
    )
    p_bench.add_argument(
        "--timing",
        choices=["explicit", "simulated"],
        default=None,
        help="Override timing_mode for coord_scale/coord_risk: explicit (deterministic) or simulated (latency/TAT realism). Uses scale default if omitted.",
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
        help="Pipeline mode: deterministic (scripted only) | llm_offline (LLM interface, deterministic backend only) | llm_live (network LLM; requires --allow-network). See docs/agents/llm_live.md.",
    )
    p_bench.add_argument(
        "--coord-fixtures-path",
        type=Path,
        default=None,
        help="Path to coordination_fixtures.json dir for replay (llm_offline). Omit to use deterministic backend.",
    )
    p_bench.add_argument(
        "--record-coord-fixtures-path",
        type=Path,
        default=None,
        help="Path to write coordination_fixtures.json when running coord task (record mode).",
    )
    p_bench.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network for live LLM backends (required for --llm-backend openai_live/ollama_live); also LABTRUST_ALLOW_NETWORK=1",
    )
    _coord_backend_choices = [
        "inherit",
        "openai_live",
        "ollama_live",
        "anthropic_live",
        "openai_responses",
        "deterministic",
    ]
    p_bench.add_argument(
        "--coord-planner-backend",
        choices=_coord_backend_choices,
        default=None,
        help="Backend for coordinator planner role (proposal/allocator). Default: inherit (use --llm-backend).",
    )
    p_bench.add_argument(
        "--coord-bidder-backend",
        choices=_coord_backend_choices,
        default=None,
        help="Backend for coordinator bidder role (auction). Default: inherit (use --llm-backend).",
    )
    p_bench.add_argument(
        "--coord-repair-backend",
        choices=_coord_backend_choices,
        default=None,
        help="Backend for coordinator repair role. Default: inherit (use --llm-backend).",
    )
    p_bench.add_argument(
        "--coord-detector-backend",
        choices=_coord_backend_choices,
        default=None,
        help="Backend for coordinator detector role. Default: inherit (use --llm-backend).",
    )
    p_bench.add_argument(
        "--coord-planner-model",
        default=None,
        help="Model for coordinator planner role. Default: inherit (use --llm-model).",
    )
    p_bench.add_argument(
        "--coord-bidder-model",
        default=None,
        help="Model for coordinator bidder role. Default: inherit (use --llm-model).",
    )
    p_bench.add_argument(
        "--coord-repair-model",
        default=None,
        help="Model for coordinator repair role. Default: inherit (use --llm-model).",
    )
    p_bench.add_argument(
        "--coord-detector-model",
        default=None,
        help="Model for coordinator detector role. Default: inherit (use --llm-model).",
    )
    p_bench.add_argument(
        "--profile",
        default=None,
        choices=["llm_live_eval"],
        help="Preset: llm_live_eval = adversarial_disruption, insider_key_misuse, coord_risk with llm_live + allow-network, writes LLM_TRACE/ (requires --allow-network).",
    )
    p_bench.add_argument(
        "--agent-driven",
        action="store_true",
        help="Run in agent-centric mode: LLM drives the loop via step_lab tool. Requires --coord-method.",
    )
    p_bench.add_argument(
        "--multi-agentic",
        action="store_true",
        help="With --agent-driven: N agents each submit via submit_my_action; coordinator combines and steps (requires --coord-method).",
    )
    p_bench.add_argument(
        "--resume-from",
        type=Path,
        default=None,
        metavar="DIR",
        help="Resume from a previous run: load checkpoint from DIR and skip completed episodes (DIR must contain checkpoint.json; use same --out/--log as original run).",
    )
    p_bench.add_argument(
        "--checkpoint-every",
        type=int,
        default=None,
        metavar="N",
        help="Write a checkpoint every N episodes to the run directory (derived from --log). Enables resume with --resume-from.",
    )
    p_bench.add_argument(
        "--log-step-interval",
        type=int,
        default=0,
        metavar="N",
        help="When --log is set: append a step record to run_dir/steps.jsonl every N steps (0=off, 1=every step). Default: 0.",
    )
    p_bench.add_argument(
        "--checkpoint-every-steps",
        type=int,
        default=0,
        metavar="N",
        help="When --log is set: write step checkpoint every N steps to run_dir (0=off). Best-effort resume; same code version recommended.",
    )
    p_bench.add_argument(
        "--always-step-timing",
        action="store_true",
        help="Always record step_timing and run_duration_wall_s in metadata (for capacity planning). When set, timing is recorded even for deterministic runs; may affect determinism if metadata is hashed.",
    )
    p_bench.add_argument(
        "--approval-hook",
        choices=("none", "auto_approve"),
        default="none",
        help="Optional approval hook: none (default) or auto_approve (pass-through). When set, proposed actions are transformed after propose_actions and before env.step; the benchmark does not define human behavior.",
    )
    p_bench.set_defaults(func=_run_benchmark)
    p_bench_smoke = sub.add_parser(
        "bench-smoke",
        help="Run 1 episode per task (throughput_sla, stat_insertion, qc_cascade); regression smoke.",
    )
    p_bench_smoke.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed for episodes (default 42)",
    )
    p_bench_smoke.set_defaults(func=_run_bench_smoke)
    p_throughput_compare = sub.add_parser(
        "throughput-compare",
        help="Run throughput_sla with scripted baseline and print mean throughput (for throughput-focused comparison).",
    )
    p_throughput_compare.add_argument(
        "--episodes",
        type=int,
        default=10,
        help="Number of episodes (default 10)",
    )
    p_throughput_compare.add_argument(
        "--out",
        default="throughput_compare_results.json",
        help="Output results JSON path (default throughput_compare_results.json)",
    )
    p_throughput_compare.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Base seed (default 123)",
    )
    p_throughput_compare.set_defaults(func=_run_throughput_compare)
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
        choices=["deterministic", "openai_live", "ollama_live", "anthropic_live"],
        default=None,
        help="Include LLM coordination methods: deterministic, openai_live, or ollama_live. Omit to run only non-LLM methods.",
    )
    p_coord_study.add_argument(
        "--llm-model",
        default=None,
        help="Optional LLM model when using --llm-backend openai_live (e.g. gpt-4o).",
    )
    p_coord_study.add_argument(
        "--emit-coordination-matrix",
        action="store_true",
        default=False,
        help="After the study, build CoordinationMatrix v0.1 into the run directory (llm_live only; errors if pipeline is not llm_live).",
    )
    p_coord_study.add_argument(
        "--partner",
        default=None,
        metavar="ID",
        help="Partner overlay ID; use policy/partners/<id>/coordination/coordination_study_spec.v0.1.yaml as spec when present (overrides --spec path).",
    )
    p_coord_study.set_defaults(func=_run_coordination_study)
    p_coord_security_pack = sub.add_parser(
        "run-coordination-security-pack",
        help="Run internal coordination security regression pack: scale x method x injection matrix, deterministic, 1 ep/cell. Writes pack_results/, pack_summary.csv, pack_gate.md.",
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
    p_coord_security_pack.add_argument(
        "--methods-from",
        default="fixed",
        metavar="MODE_OR_PATH",
        help="Methods: fixed (config default), full (all from policy except marl_ppo), full_llm (LLM-based coordination methods only), or path to file (one method_id per line or YAML list).",
    )
    p_coord_security_pack.add_argument(
        "--injections-from",
        default="fixed",
        metavar="MODE_OR_PATH",
        help="Injections: fixed (config default), critical (short list), policy (injections.v0.2 + registry), or path to file.",
    )
    p_coord_security_pack.add_argument(
        "--scales-from",
        default="default",
        choices=("default", "full"),
        help="Scales: default (2 scales), full (all 3 scales: small_smoke, medium_stress_signed_bus, corridor_heavy).",
    )
    p_coord_security_pack.add_argument(
        "--matrix-preset",
        default=None,
        metavar="NAME",
        help="Use matrix preset from policy (e.g. hospital_lab): overrides scale/method/injection lists.",
    )
    p_coord_security_pack.add_argument(
        "--scale-ids",
        nargs="+",
        default=None,
        metavar="SCALE",
        help="Run only these scale_ids (e.g. small_smoke). Use with --matrix-preset full_matrix to run one scale at a time.",
    )
    p_coord_security_pack.add_argument(
        "--partner",
        default=None,
        help="Partner overlay ID (e.g. hsl_like); effective policy merged for each pack cell.",
    )
    p_coord_security_pack.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel workers for pack cells (default 1 = sequential). Use e.g. 4 or 8 to speed up large matrices.",
    )
    p_coord_security_pack.add_argument(
        "--llm-backend",
        default=None,
        metavar="BACKEND",
        choices=("deterministic", "openai_live", "openai_responses", "ollama_live", "anthropic_live", "openai_hosted"),
        help="LLM backend for coordination/agents (default: deterministic). Use openai_live etc. to benchmark LLM methods with live API; requires --allow-network.",
    )
    p_coord_security_pack.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network for live LLM backends (required when --llm-backend is openai_live, ollama_live, etc.).",
    )
    p_coord_security_pack.set_defaults(func=_run_coordination_security_pack)
    p_build_matrix = sub.add_parser(
        "build-coordination-matrix",
        help="Build CoordinationMatrix v0.1 from an llm_live coordination run directory.",
    )
    p_build_matrix.add_argument(
        "--run",
        required=True,
        help="Run directory (llm_live coordination study output with summary/ and metadata).",
    )
    p_build_matrix.add_argument(
        "--out",
        required=True,
        help="Output path (JSON file) or directory; if directory, writes coordination_matrix.v0.1.json",
    )
    p_build_matrix.add_argument(
        "--policy-root",
        default=None,
        help="Policy root for inputs/column_map/spec (default: repo policy dir).",
    )
    p_build_matrix.add_argument(
        "--no-strict",
        action="store_true",
        help="If set, do not require pipeline_mode to be discoverable (not recommended).",
    )
    p_build_matrix.add_argument(
        "--matrix-mode",
        choices=("llm_live", "pack"),
        default="llm_live",
        help="llm_live: require llm_live run and summary_coord; pack: allow pack-only dir, derive clean from pack_summary baseline.",
    )
    p_build_matrix.set_defaults(func=_run_build_coordination_matrix)
    p_recommend = sub.add_parser(
        "recommend-coordination-method",
        help="Produce coordination decision artifact from run dir: COORDINATION_DECISION.v0.1.json and COORDINATION_DECISION.md (objective + constraints from selection policy).",
    )
    p_recommend.add_argument(
        "--run",
        required=True,
        help="Run directory containing pack_summary.csv or summary/summary_coord.csv",
    )
    p_recommend.add_argument(
        "--out",
        required=True,
        help="Output directory for COORDINATION_DECISION.v0.1.json and COORDINATION_DECISION.md",
    )
    p_recommend.add_argument(
        "--policy-root",
        default=None,
        help="Policy root (default: repo root); selection policy and schema loaded from here.",
    )
    p_recommend.set_defaults(func=_run_recommend_coordination_method)
    p_summarize_coord = sub.add_parser(
        "summarize-coordination",
        help="Aggregate coordination results: read summary_coord.csv from --in, write SOTA leaderboard and method-class comparison to --out.",
    )
    p_summarize_coord.add_argument(
        "--in",
        dest="in_dir",
        required=True,
        help="Input run directory containing summary/summary_coord.csv (or summary_coord.csv).",
    )
    p_summarize_coord.add_argument(
        "--out",
        dest="out_dir",
        required=True,
        help="Output directory for summary/sota_leaderboard.csv, sota_leaderboard.md, method_class_comparison.csv, method_class_comparison.md.",
    )
    p_summarize_coord.set_defaults(func=_run_summarize_coordination)
    p_lab_report = sub.add_parser(
        "build-lab-coordination-report",
        help="Bundle summarize + recommend from pack output; write LAB_COORDINATION_REPORT.md and artifacts.",
    )
    p_lab_report.add_argument(
        "--pack-dir",
        required=True,
        help="Directory containing pack_summary.csv (and optionally pack_gate.md, SECURITY/).",
    )
    p_lab_report.add_argument(
        "--out",
        default=None,
        help="Output directory for summary/, COORDINATION_DECISION.*, and LAB_COORDINATION_REPORT.md (default: pack-dir).",
    )
    p_lab_report.add_argument(
        "--policy-root",
        default=None,
        help="Policy root for selection policy (default: repo root).",
    )
    p_lab_report.add_argument(
        "--matrix-preset",
        default=None,
        metavar="NAME",
        help="Matrix preset name for report scope (e.g. hospital_lab).",
    )
    p_lab_report.add_argument(
        "--include-matrix",
        action="store_true",
        help="Also build CoordinationMatrix from pack (pack mode) and add coordination_matrix.v0.1.json to artifacts.",
    )
    p_lab_report.add_argument(
        "--partner",
        default=None,
        help="Partner overlay ID; selection policy loaded from partner overlay when present.",
    )
    p_lab_report.set_defaults(func=_run_build_lab_coordination_report)
    p_forker_quickstart = sub.add_parser(
        "forker-quickstart",
        help="One-command forker flow: validate-policy, run pack (fixed + critical), build report, export risk register; print artifact paths.",
    )
    p_forker_quickstart.add_argument(
        "--out",
        required=True,
        help="Output directory; pack and risk register written under it.",
    )
    p_forker_quickstart.add_argument(
        "--partner",
        default=None,
        metavar="ID",
        help="Optional partner overlay ID for validate, pack, report, and export.",
    )
    p_forker_quickstart.set_defaults(func=_run_forker_quickstart)
    p_live_orch = sub.add_parser(
        "run-live-orchestrator",
        help="Live orchestrator: run chosen coordination method (llm_live or deterministic), emit run dir with matrix + decision + receipts + defense transition. Verify with verify-bundle.",
    )
    p_live_orch.add_argument(
        "--run-dir",
        required=True,
        help="Output run directory (cells/, summary/, decision/, receipts/, defense_transition).",
    )
    p_live_orch.add_argument(
        "--method",
        required=True,
        help="Coordination method id (from COORDINATION_DECISION or policy).",
    )
    p_live_orch.add_argument(
        "--scale",
        default="small_smoke",
        help="Scale config id (default: small_smoke).",
    )
    p_live_orch.add_argument(
        "--injection",
        default=None,
        help="Optional risk injection id (e.g. INJ-COMMS-POISON-001). Omit for baseline.",
    )
    p_live_orch.add_argument(
        "--episodes",
        type=int,
        default=1,
        help="Number of episodes (default: 1).",
    )
    p_live_orch.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed (default: 42).",
    )
    p_live_orch.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network for llm_live backends.",
    )
    p_live_orch.add_argument(
        "--llm-backend",
        default="deterministic",
        help="LLM backend: deterministic, openai_live, ollama_live (default: deterministic).",
    )
    p_live_orch.add_argument(
        "--llm-model",
        default=None,
        help="Optional model for openai_live (e.g. gpt-4o).",
    )
    p_live_orch.add_argument(
        "--policy-root",
        default=None,
        help="Policy root (default: repo root).",
    )
    p_live_orch.set_defaults(func=_run_live_orchestrator)
    p_plots = sub.add_parser(
        "make-plots",
        help="Generate figures and data tables from a study run (out_dir/figures/)",
    )
    p_plots.add_argument(
        "--run",
        required=True,
        help="Study output directory (e.g. runs/<id>)",
    )
    p_plots.add_argument(
        "--theme",
        choices=("light", "dark"),
        default="light",
        help="Figure theme: light (default) or dark.",
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
    p_validate_fhir = sub.add_parser(
        "validate-fhir",
        help="Validate FHIR Bundle coded elements against a terminology value set (optional extension; not part of minimal benchmark).",
    )
    p_validate_fhir.add_argument(
        "--bundle",
        required=True,
        help="Path to FHIR Bundle JSON file (e.g. fhir_bundle.json from export-fhir)",
    )
    p_validate_fhir.add_argument(
        "--terminology",
        required=True,
        help="Path to terminology value set JSON (value_sets: map system URI to list of allowed codes)",
    )
    p_validate_fhir.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any coded element is outside the value set",
    )
    p_validate_fhir.set_defaults(func=_run_validate_fhir)
    p_verify_bundle = sub.add_parser(
        "verify-bundle",
        help="Verify a single EvidenceBundle.v0.1: manifest integrity, schema, hashchain, invariant trace",
    )
    p_verify_bundle.add_argument(
        "--bundle",
        required=True,
        help="EvidenceBundle.v0.1 directory (must contain manifest.json; use a path under receipts/.../EvidenceBundle.v0.1, not the release root)",
    )
    p_verify_bundle.add_argument(
        "--allow-extra-files",
        action="store_true",
        help="Do not fail on files present but not in manifest (e.g. fhir_bundle.json)",
    )
    p_verify_bundle.add_argument(
        "--strict-fingerprints",
        action="store_true",
        help="Require coordination_policy_fingerprint, memory_policy_fingerprint, rbac_policy_fingerprint, tool_registry_fingerprint in manifest (default for releases)",
    )
    p_verify_bundle.set_defaults(func=_run_verify_bundle)
    p_verify_release = sub.add_parser(
        "verify-release",
        help="Verify all EvidenceBundle.v0.1 dirs under a release (package-release output); exits non-zero if any bundle fails",
    )
    p_verify_release.add_argument(
        "--release-dir",
        required=True,
        help="Release directory (output of package-release; contains receipts/ and MANIFEST.v0.1.json)",
    )
    p_verify_release.add_argument(
        "--allow-extra-files",
        action="store_true",
        help="Do not fail on files present but not in manifest (passed to each verify-bundle)",
    )
    p_verify_release.add_argument(
        "--quiet",
        action="store_true",
        help="Only print summary; stop on first failure",
    )
    p_verify_release.add_argument(
        "--strict-fingerprints",
        action="store_true",
        help="Require all bundle manifests to include coordination, memory, rbac, tool_registry fingerprints (default for releases)",
    )
    p_verify_release.set_defaults(func=_run_verify_release)
    p_build_release_manifest = sub.add_parser(
        "build-release-manifest",
        help="Write RELEASE_MANIFEST.v0.1.json with hashes of evidence bundles, MANIFEST, and risk register bundle (if present). Use before verify-release for full artifact verification.",
    )
    p_build_release_manifest.add_argument(
        "--release-dir",
        required=True,
        help="Release directory (output of package-release; may contain RISK_REGISTER_BUNDLE.v0.1.json if export-risk-register was run with --out <release-dir>)",
    )
    p_build_release_manifest.set_defaults(func=_run_build_release_manifest)
    p_check_gate = sub.add_parser(
        "check-security-gate",
        help="Check coordination security pack gate: exit 0 if pack_gate.md has no FAIL, else exit 1.",
    )
    p_check_gate.add_argument(
        "--run",
        required=True,
        help="Run directory containing pack_gate.md (e.g. output of run-coordination-security-pack).",
    )
    p_check_gate.set_defaults(func=_run_check_security_gate)
    p_ui_export = sub.add_parser(
        "ui-export",
        help="Export UI-ready bundle (index, events, receipts_index, reason_codes) from a run dir",
    )
    p_ui_export.add_argument(
        "--run",
        required=True,
        help="Run directory: labtrust_runs/quick_eval_*, package-release output, or full-pipeline (baselines/, SECURITY/, coordination_pack/)",
    )
    p_ui_export.add_argument(
        "--out",
        required=True,
        help="Output path for ui_bundle.zip",
    )
    p_ui_export.set_defaults(func=_run_ui_export)
    p_build_episode_bundle = sub.add_parser(
        "build-episode-bundle",
        help="Build episode_bundle.json for the simulation viewer from a run directory",
    )
    p_build_episode_bundle.add_argument(
        "--run-dir",
        required=True,
        metavar="PATH",
        help="Run directory (episode_log.jsonl or logs/*.jsonl, optional METHOD_TRACE, coord_decisions)",
    )
    p_build_episode_bundle.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Output path (default: <run-dir>/episode_bundle.json)",
    )
    p_build_episode_bundle.set_defaults(func=_run_build_episode_bundle)
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
        help="Run directory or glob (e.g. tests/fixtures/ui_fixtures, labtrust_runs/*); can be repeated",
    )
    p_export_risk.add_argument(
        "--partner",
        default=None,
        metavar="ID",
        help="Partner overlay ID; load risk registry and security suite from policy/partners/<id>/ when present",
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
    p_validate_cov = sub.add_parser(
        "validate-coverage",
        help="Validate risk register bundle coverage (required_bench cells evidenced or waived). With --strict, exit 1 if any required risk has missing evidence.",
    )
    p_validate_cov.add_argument(
        "--bundle",
        default=None,
        metavar="PATH",
        help="Path to RISK_REGISTER_BUNDLE.v0.1.json (default: <repo_root>/risk_register_out/RISK_REGISTER_BUNDLE.v0.1.json if --out not set)",
    )
    p_validate_cov.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help="Directory containing RISK_REGISTER_BUNDLE.v0.1.json (used when --bundle not set)",
    )
    p_validate_cov.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit 1) if any required_bench (method_id, risk_id) has no present evidence and is not waived",
    )
    p_validate_cov.set_defaults(func=_run_validate_coverage)
    p_show_risk_matrix = sub.add_parser(
        "show-method-risk-matrix",
        help="Print or export method x risk coverage matrix (from policy/coordination/method_risk_matrix.v0.1.yaml).",
    )
    p_show_risk_matrix.add_argument(
        "--format",
        choices=("table", "csv", "markdown"),
        default="table",
        help="Output format: table (terminal), csv (Excel), markdown.",
    )
    p_show_risk_matrix.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write output to file (default: stdout).",
    )
    p_show_risk_matrix.add_argument(
        "--policy-root",
        default=None,
        help="Policy root (default: repo root); matrix YAML path under policy/coordination/.",
    )
    p_show_risk_matrix.set_defaults(func=_run_show_method_risk_matrix)
    p_show_pack_matrix = sub.add_parser(
        "show-pack-matrix",
        help="Print or export pack matrix (method x scale x injection) with scale taxonomy (num_agents).",
    )
    p_show_pack_matrix.add_argument(
        "--format",
        choices=("table", "csv", "markdown"),
        default="table",
        help="Output format: table (terminal), csv (Excel), markdown.",
    )
    p_show_pack_matrix.add_argument(
        "--matrix-preset",
        default=None,
        help="Use matrix preset from coordination_security_pack (e.g. hospital_lab).",
    )
    p_show_pack_matrix.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write output to file (default: stdout).",
    )
    p_show_pack_matrix.add_argument(
        "--policy-root",
        default=None,
        help="Policy root (default: repo root).",
    )
    p_show_pack_matrix.set_defaults(func=_run_show_pack_matrix)
    p_show_pack_results = sub.add_parser(
        "show-pack-results",
        help="Show result matrix from a completed pack run (real results from run-coordination-security-pack).",
    )
    p_show_pack_results.add_argument(
        "--run",
        required=True,
        metavar="DIR",
        help="Pack run directory containing pack_summary.csv and SECURITY/coordination_risk_matrix.*",
    )
    p_show_pack_results.add_argument(
        "--format",
        choices=("markdown", "table", "csv"),
        default="markdown",
        help="Output format: markdown (full matrix with verdicts), table (terminal), csv.",
    )
    p_show_pack_results.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write output to file (default: stdout).",
    )
    p_show_pack_results.set_defaults(func=_run_show_pack_results)
    p_repro = sub.add_parser(
        "reproduce",
        help="Reproduce minimal results and figures (study sweep + plots)",
    )
    p_repro.add_argument(
        "--profile",
        required=True,
        choices=["minimal", "full", "full_with_coordination"],
        help="minimal: small sweep, few episodes; full: same sweep, more episodes; full_with_coordination: full + coordination pack + lab report",
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
        help="minimal or full reproduce profile; paper_v0.1 = benchmark-first (baselines + insider_key_misuse study + summarize + receipts + FIGURES/TABLES)",
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
        help="Pipeline mode: deterministic | llm_offline | llm_live (default: deterministic). See docs/agents/llm_live.md.",
    )
    p_package_release.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network (only with --pipeline-mode llm_live); default: disabled",
    )
    p_package_release.add_argument(
        "--include-coordination-pack",
        action="store_true",
        help="(paper_v0.1 only) Run coordination security pack into _coordination_pack/ and build lab report.",
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
    p_security_suite.add_argument(
        "--timeout",
        type=int,
        default=120,
        metavar="SECS",
        help="Max seconds per test_ref pytest run (default 120)",
    )
    p_security_suite.add_argument(
        "--llm-attacker",
        action="store_true",
        help="Include LLM-attacker attacks (live LLM generates adversarial payloads). Requires --allow-network and --llm-backend. Default: off (deterministic only).",
    )
    p_security_suite.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network (required for --llm-attacker). Set LABTRUST_ALLOW_NETWORK=1 to allow.",
    )
    p_security_suite.add_argument(
        "--llm-backend",
        choices=["openai_live", "ollama_live", "anthropic_live"],
        default=None,
        help="Live LLM backend for attacker payload generation (required with --llm-attacker).",
    )
    p_security_suite.add_argument(
        "--llm-model",
        default=None,
        metavar="MODEL",
        help="Optional model override for --llm-backend (e.g. gpt-4o, llama3.2).",
    )
    p_security_suite.add_argument(
        "--llm-attacker-max-chars",
        type=int,
        default=2000,
        metavar="N",
        help="Max characters for LLM-generated payload (default 2000). Use higher (e.g. 4000) for stress tests.",
    )
    p_security_suite.add_argument(
        "--llm-attacker-rounds",
        type=int,
        default=None,
        metavar="N",
        help="Rounds for iterative LLM attacker (default 1). When N>1, attacker receives block feedback and generates follow-up payloads; pass iff no round succeeds.",
    )
    p_security_suite.add_argument(
        "--skip-system-level",
        action="store_true",
        help="Skip coord_pack_ref (system-level coordination-under-attack) entries; use when [env] is not installed.",
    )
    p_security_suite.add_argument(
        "--agent-driven-mode",
        choices=["single", "multi_agentic"],
        default=None,
        help="When set, scenario_ref and llm_attacker attacks use agent-driven entry points (single or multi_agentic).",
    )
    p_security_suite.add_argument(
        "--use-full-driver-loop",
        action="store_true",
        help="When set with --agent-driven-mode, use full driver loop (minimal env + AgentDrivenDriver + run_episode_agent_driven) for scenario_ref/llm_attacker. Default: in-process check.",
    )
    p_security_suite.add_argument(
        "--use-mock-env",
        action="store_true",
        help="When set with --use-full-driver-loop, use MockBenchmarkEnv instead of full sim for agent-driven scenario_ref/llm_attacker (no CoreEnv dependency).",
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
    p_audit_selfcheck = sub.add_parser(
        "audit-selfcheck",
        help="Run Phase A audit checks (no-placeholders, validate-policy, export-risk-register from fixtures, risk register contract gate); write AUDIT_SELF_CHECK.json for reviewer sharing.",
    )
    p_audit_selfcheck.add_argument(
        "--out",
        required=True,
        help="Output directory; AUDIT_SELF_CHECK.json and risk_register_out/ written here",
    )
    p_audit_selfcheck.set_defaults(func=_run_audit_selfcheck)
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
    p_run_summary = sub.add_parser(
        "run-summary",
        help="Print one-line stats (episodes, steps, violations, throughput) for a run directory",
    )
    p_run_summary.add_argument(
        "--run",
        required=True,
        help="Run directory (containing results.json or episodes.jsonl)",
    )
    p_run_summary.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: text (one-line) or json (default: text)",
    )
    p_run_summary.set_defaults(func=_run_run_summary)
    p_gen_baselines = sub.add_parser(
        "generate-official-baselines",
        help="Regenerate and freeze official baseline results (core tasks from registry); write results/, summary.csv, summary.md, metadata.json. Refuse to overwrite unless --force.",
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
        help="Pipeline mode: deterministic | llm_offline | llm_live (default: deterministic). See docs/agents/llm_live.md.",
    )
    p_official_pack.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network (only with --pipeline-mode llm_live); default: disabled",
    )
    p_official_pack.add_argument(
        "--llm-backend",
        default=None,
        help="When --pipeline-mode llm_live: backend to use (e.g. openai_responses, anthropic_live, ollama_live).",
    )
    p_official_pack.add_argument(
        "--include-coordination-pack",
        action="store_true",
        help="Run coordination security pack into coordination_pack/ and build lab report (or set coordination_pack.enabled in pack policy).",
    )
    p_official_pack.add_argument(
        "--partner",
        default=None,
        metavar="ID",
        help="Partner overlay ID; load benchmark pack from policy/partners/<id>/official/ when present.",
    )
    p_official_pack.set_defaults(func=_run_official_pack)
    p_cross_provider = sub.add_parser(
        "run-cross-provider-pack",
        help="Run official pack once per provider (llm_live); emit per-provider dirs and merged summary.",
    )
    p_cross_provider.add_argument(
        "--out",
        required=True,
        help="Output directory; each provider writes to <out>/<provider>/",
    )
    p_cross_provider.add_argument(
        "--providers",
        required=True,
        help="Comma-separated list (e.g. openai_live,anthropic_live,ollama_live)",
    )
    p_cross_provider.add_argument(
        "--seed-base",
        type=int,
        default=100,
        help="Base seed (default 100)",
    )
    p_cross_provider.add_argument(
        "--smoke",
        action="store_true",
        default=True,
        help="Use smoke settings (default True)",
    )
    p_cross_provider.add_argument(
        "--no-smoke",
        action="store_true",
        help="Disable smoke; run full pack per provider",
    )
    p_cross_provider.set_defaults(func=_run_cross_provider_pack)
    from labtrust_gym.cli.eval_agent import register_parser as register_eval_agent

    register_eval_agent(sub)
    p_determinism = sub.add_parser(
        "determinism-report",
        help="Run benchmark twice with identical args; produce determinism_report.md and .json; assert v0.2 metrics and episode log hash identical.",
    )
    p_determinism.add_argument(
        "--task",
        required=True,
        help="Task name (e.g. throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse)",
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
        help="Coordination method for coord_scale / coord_risk (e.g. kernel_centralized_edf). Defaults to kernel_centralized_edf when task is coord_scale or coord_risk.",
    )
    p_determinism.add_argument(
        "--pipeline-mode",
        choices=["deterministic", "llm_offline"],
        default=None,
        help="Pipeline mode: deterministic or llm_offline. Omit to use runner default (deterministic for throughput_sla).",
    )
    p_determinism.add_argument(
        "--llm-backend",
        default=None,
        help="LLM backend when --pipeline-mode llm_offline (e.g. deterministic, deterministic_constrained).",
    )
    p_determinism.add_argument(
        "--injection",
        default=None,
        help="Risk injection id for coord_risk (e.g. none).",
    )
    p_determinism.set_defaults(func=_run_determinism_report)
    p_quick_eval = sub.add_parser(
        "quick-eval",
        help="Run 1 episode each of throughput_sla, adversarial_disruption, multi_site_stat with scripted baselines; write markdown summary and logs under ./labtrust_runs/",
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
        help="Pipeline mode: deterministic | llm_offline | llm_live (default: deterministic). llm_live requires --allow-network. See docs/agents/llm_live.md.",
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
        choices=["openai_live", "openai_responses", "anthropic_live", "ollama_live"],
        default="openai_responses",
        help="Backend to check (default: openai_responses). openai_live uses legacy Chat Completions; openai_responses uses Responses API; anthropic_live uses Anthropic Messages API.",
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
    p_record_fixtures = sub.add_parser(
        "record-llm-fixtures",
        help="Run a short benchmark with a live LLM backend and record (message_digest, response) to tests/fixtures/llm_responses/. Run manually with network; not for CI.",
    )
    p_record_fixtures.add_argument(
        "--llm-backend",
        default="openai_hosted",
        choices=["openai_hosted", "openai_live", "openai_responses", "anthropic_live", "ollama_live"],
        help="Live backend to use for recording (default: openai_hosted).",
    )
    p_record_fixtures.add_argument(
        "--llm-model",
        default=None,
        help="Optional model override (e.g. gpt-4o-mini, llama3.2). Backend-specific env vars apply when unset.",
    )
    p_record_fixtures.add_argument(
        "--task",
        default="insider_key_misuse",
        help="Task to run (default: insider_key_misuse). Use a task that exercises LLM agents.",
    )
    p_record_fixtures.add_argument(
        "--episodes",
        type=int,
        default=1,
        help="Number of episodes (default: 1).",
    )
    p_record_fixtures.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed (default: 42).",
    )
    p_record_fixtures.add_argument(
        "--out",
        default="runs/record_fixtures/results.json",
        help="Output path for run results (default: runs/record_fixtures/results.json).",
    )
    p_record_fixtures.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root; default from get_repo_root().",
    )
    p_record_fixtures.set_defaults(func=_run_record_llm_fixtures)
    p_record_coord_fixtures = sub.add_parser(
        "record-coordination-fixtures",
        help="Run coord_risk (or coord_scale) with a live coordination backend and record proposal/bid responses to coordination_fixtures.json. Manual use with network; not for CI.",
    )
    p_record_coord_fixtures.add_argument(
        "--coord-method",
        default="llm_central_planner",
        choices=["llm_central_planner", "llm_auction_bidder"],
        help="Coordination method to record (default: llm_central_planner).",
    )
    p_record_coord_fixtures.add_argument(
        "--task",
        default="coord_risk",
        choices=["coord_risk", "coord_scale"],
        help="Task (default: coord_risk).",
    )
    p_record_coord_fixtures.add_argument(
        "--llm-backend",
        default="openai_live",
        choices=["openai_live", "ollama_live", "anthropic_live"],
        help="Live backend for coordination (default: openai_live).",
    )
    p_record_coord_fixtures.add_argument(
        "--episodes",
        type=int,
        default=1,
        help="Number of episodes (default: 1).",
    )
    p_record_coord_fixtures.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed (default: 42).",
    )
    p_record_coord_fixtures.add_argument(
        "--out",
        default="runs/record_coord_fixtures/results.json",
        help="Output path for run results.",
    )
    p_record_coord_fixtures.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root; default from get_repo_root().",
    )
    p_record_coord_fixtures.set_defaults(func=_run_record_coordination_fixtures)
    p_replay_fixtures = sub.add_parser(
        "replay-from-fixtures",
        help="Replay a benchmark from recorded fixtures (no network). Uses llm_offline + deterministic + coord-fixtures-path for coord tasks.",
    )
    p_replay_fixtures.add_argument(
        "--task",
        required=True,
        help="Task name (e.g. insider_key_misuse, coord_risk).",
    )
    p_replay_fixtures.add_argument(
        "--episodes",
        type=int,
        default=1,
        help="Number of episodes (default: 1).",
    )
    p_replay_fixtures.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base seed (default: 42). Must match the seed used when recording.",
    )
    p_replay_fixtures.add_argument(
        "--coord-method",
        default=None,
        help="Coordination method for coord_risk/coord_scale (e.g. llm_central_planner). Required when task is coord_risk or coord_scale.",
    )
    p_replay_fixtures.add_argument(
        "--coord-fixtures-path",
        type=Path,
        default=None,
        help="Path to dir containing coordination_fixtures.json (default: repo tests/fixtures/llm_responses).",
    )
    p_replay_fixtures.add_argument(
        "--out",
        default=None,
        help="Output results path (default: runs/replay_from_fixtures/<task>_results.json).",
    )
    p_replay_fixtures.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root; default from get_repo_root().",
    )
    p_replay_fixtures.set_defaults(func=_run_replay_from_fixtures)
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
        help="Train PPO on throughput_sla (or other task); requires [marl] extra",
    )
    p_train_ppo.add_argument("--task", default="throughput_sla", help="Task name (default throughput_sla)")
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
    p_train_ppo.add_argument(
        "--net-arch",
        default=None,
        help="Policy MLP hidden sizes, comma-separated (e.g. 128,128); default 64,64",
    )
    p_train_ppo.add_argument(
        "--checkpoint-every",
        type=int,
        default=None,
        help="Save checkpoint every N steps; with --keep-best run eval and keep best",
    )
    p_train_ppo.add_argument(
        "--keep-best",
        type=int,
        default=0,
        help="When using --checkpoint-every, keep best model by eval mean_reward (1=save best_model.zip)",
    )
    p_train_ppo.add_argument(
        "--train-config",
        default=None,
        metavar="PATH",
        help="Path to JSON train config (net_arch, obs_history_len, learning_rate, n_steps, reward_scale_schedule). CLI --net-arch overrides net_arch in file.",
    )
    p_train_ppo.add_argument(
        "--obs-history-len",
        type=int,
        default=None,
        metavar="N",
        help="Stack last N observations (partial observability); overrides train_config file if set.",
    )
    p_train_ppo.add_argument(
        "--learning-rate",
        type=float,
        default=None,
        metavar="LR",
        help="PPO learning rate; overrides train_config file if set.",
    )
    p_train_ppo.add_argument(
        "--n-steps",
        type=int,
        default=None,
        metavar="N",
        help="PPO n_steps per update; overrides train_config file if set.",
    )
    p_train_ppo.set_defaults(func=_run_train_ppo)
    p_eval_ppo = sub.add_parser(
        "eval-ppo",
        help="Evaluate trained PPO policy; requires [marl] extra",
    )
    p_eval_ppo.add_argument("--model", required=True, help="Path to model.zip")
    p_eval_ppo.add_argument("--task", default="throughput_sla", help="Task name")
    p_eval_ppo.add_argument("--episodes", type=int, default=50, help="Evaluation episodes")
    p_eval_ppo.add_argument("--seed", type=int, default=123, help="Random seed")
    p_eval_ppo.add_argument("--out", default=None, help="Output JSON path for metrics")
    p_eval_ppo.set_defaults(func=_run_eval_ppo)
    args = parser.parse_args()
    # Set up CLI output and logging from global verbosity.
    verbosity = verbosity_from_args(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "global_quiet", False),
    )
    console = CLIOutput(verbosity=verbosity)
    set_console(console)
    configure_cli_logging(verbosity)
    # Apply lab profile when --profile is set (override partner_id and optional provider/paths).
    profile_id = getattr(args, "profile", None)
    if profile_id:
        root = get_repo_root()
        profile = load_lab_profile(root, profile_id)
        if profile:
            if profile.get("partner_id") is not None:
                setattr(args, "partner", profile["partner_id"])
            if profile.get("security_suite_provider_id") is not None:
                setattr(args, "security_suite_provider_id", profile["security_suite_provider_id"])
            if profile.get("safety_case_provider_id") is not None:
                setattr(args, "safety_case_provider_id", profile["safety_case_provider_id"])
            if profile.get("metrics_aggregator_id") is not None:
                setattr(args, "metrics_aggregator_id", profile["metrics_aggregator_id"])
            extension_packages = profile.get("extension_packages")
            if isinstance(extension_packages, list):
                import importlib

                for pkg in extension_packages:
                    if isinstance(pkg, str) and pkg.strip():
                        try:
                            importlib.import_module(pkg.strip())
                        except Exception:
                            pass
            from labtrust_gym.config import get_effective_path

            if profile.get("security_suite_path") is not None:
                setattr(
                    args,
                    "security_suite_path",
                    get_effective_path(root, profile, "security_suite_path", "golden/security_attack_suite.v0.1.yaml"),
                )
            if profile.get("safety_claims_path") is not None:
                setattr(
                    args,
                    "safety_claims_path",
                    get_effective_path(root, profile, "safety_claims_path", "safety_case/claims.v0.1.yaml"),
                )
            if profile.get("benchmark_pack_path") is not None:
                setattr(
                    args,
                    "benchmark_pack_path",
                    get_effective_path(root, profile, "benchmark_pack_path", "official/benchmark_pack.v0.1.yaml"),
                )
            if profile.get("coordination_study_spec_path") is not None:
                setattr(
                    args,
                    "coordination_study_spec_path",
                    get_effective_path(
                        root, profile, "coordination_study_spec_path", "coordination/coordination_study_spec.v0.1.yaml"
                    ),
                )
            if profile.get("domain_id") is not None:
                setattr(args, "domain_id", profile["domain_id"])
            # Validate profile provider IDs so unknown IDs fail fast with a clear message.
            pid = getattr(args, "security_suite_provider_id", None)
            if pid is not None:
                from labtrust_gym.benchmarks.security_runner import (
                    get_security_suite_provider,
                    list_security_suite_providers,
                )

                if get_security_suite_provider(pid) is None:
                    known = list_security_suite_providers()
                    get_console().error(
                        f"Profile references security_suite_provider_id {pid!r} but no provider is registered for it. Known: {known}"
                    )
                    return 1
            pid = getattr(args, "safety_case_provider_id", None)
            if pid is not None:
                from labtrust_gym.security.safety_case import (
                    get_safety_case_provider,
                    list_safety_case_providers,
                )

                if get_safety_case_provider(pid) is None:
                    known = list_safety_case_providers()
                    get_console().error(
                        f"Profile references safety_case_provider_id {pid!r} but no provider is registered for it. Known: {known}"
                    )
                    return 1
            pid = getattr(args, "metrics_aggregator_id", None)
            if pid is not None:
                from labtrust_gym.benchmarks.metrics import (
                    get_metrics_aggregator,
                    list_metrics_aggregators,
                )

                if get_metrics_aggregator(pid) is None:
                    known = list_metrics_aggregators()
                    get_console().error(
                        f"Profile references metrics_aggregator_id {pid!r} but no aggregator is registered for it. Known: {known}"
                    )
                    return 1
            did = getattr(args, "domain_id", None)
            if did is not None:
                from labtrust_gym.domain import (
                    get_domain_adapter_factory,
                    list_domains,
                )

                if get_domain_adapter_factory(did) is None:
                    known = list_domains()
                    get_console().error(
                        f"Profile references domain_id {did!r} but no domain adapter is registered for it. Known: {known}"
                    )
                    return 1
    try:
        return cast(int, args.func(args))
    except Exception as e:
        con = get_console()
        con.error(f"labtrust {getattr(args, 'command', '?')} failed: {e}")
        if con.verbosity >= Verbosity.VERBOSE:
            con.print_exception(e)
        return 1


def _run_validate_policy_wrapper(args: argparse.Namespace) -> int:
    """Run policy validation (with optional partner, strict-tool-provenance, domain)."""
    get_console().info("Running validate-policy.")
    root = get_repo_root()
    partner_id = _get_partner_id(args)
    strict_tool_provenance = getattr(args, "strict_tool_provenance", False)
    domain_id = getattr(args, "domain", None)
    return _run_validate_policy(
        root,
        partner_id=partner_id,
        strict_tool_provenance=strict_tool_provenance,
        domain_id=domain_id,
    )


def _run_validate_policy(
    root: Path,
    partner_id: str | None = None,
    strict_tool_provenance: bool = False,
    domain_id: str | None = None,
) -> int:
    """Run policy validation; print errors to stderr; return 0 on success, 1 on failure."""
    errors = validate_policy(
        root,
        partner_id=partner_id,
        strict_tool_provenance=strict_tool_provenance,
        domain_id=domain_id,
    )
    con = get_console()
    if errors:
        for e in errors:
            con.error(str(e))
        return 1
    con.write_plain("Policy validation OK.")
    if partner_id:
        con.info(f"Partner overlay {partner_id!r} validated.")
    if con.verbosity >= Verbosity.VERBOSE:
        summary_parts = [
            "Runner output contract, policy schemas, coordination security pack gate,",
            "LLM schema files, tool registry capabilities.",
        ]
        if partner_id:
            summary_parts.append(f"Partner overlay: {partner_id!r}.")
        con.panel("\n".join(summary_parts), title="Validated", border_style="dim")
    return 0


def _allow_network_from_env() -> bool:
    """True if LABTRUST_ALLOW_NETWORK is 1, true, or yes."""
    v = (os.environ.get("LABTRUST_ALLOW_NETWORK") or "").strip().lower()
    return v in ("1", "true", "yes")


def _warn_reserved_injection(injection_id: str | None) -> None:
    """If injection_id is a reserved no-op ID, print a one-line stderr warning."""
    if not injection_id:
        return
    try:
        from labtrust_gym.security.risk_injections import RESERVED_NOOP_INJECTION_IDS

        if injection_id in RESERVED_NOOP_INJECTION_IDS:
            get_console().warning(f"{injection_id!r} is a reserved no-op injection; no injection is applied.")
    except ImportError:
        pass


def _run_throughput_compare(args: argparse.Namespace) -> int:
    """Run throughput_sla with scripted baseline and print mean throughput."""
    get_console().info("Running throughput-compare (throughput_sla, scripted baseline).")
    root = get_repo_root()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from labtrust_gym.benchmarks.runner import run_benchmark

    try:
        run_benchmark(
            task_name="throughput_sla",
            num_episodes=args.episodes,
            base_seed=args.seed,
            out_path=out_path,
            repo_root=root,
        )
    except Exception as e:
        get_console().error(f"throughput-compare failed: {e}")
        return 1

    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        get_console().error(f"Could not read results: {e}")
        return 1

    episodes = data.get("episodes") or []
    if not episodes:
        get_console().write_plain("throughput_mean: (no episodes)")
        return 0

    throughputs = [(ep.get("metrics") or {}).get("throughput", 0) for ep in episodes]
    mean_tp = sum(throughputs) / len(throughputs)
    get_console().write_plain(f"throughput_mean: {mean_tp:.4f} (n={len(episodes)})")
    get_console().write_plain(f"Results written to {out_path}")
    return 0


def _run_benchmark(args: argparse.Namespace) -> int:
    """Run benchmark and write results.json."""
    get_console().info("Running run-benchmark.")
    profile = getattr(args, "profile", None)
    if profile == "llm_live_eval":
        return _run_benchmark_llm_live_eval(args)

    if not getattr(args, "task", None):
        get_console().error("run-benchmark requires --task (or use --profile llm_live_eval).")
        return 1

    from labtrust_gym.benchmarks.runner import run_benchmark as _run

    root = get_repo_root()
    partner_id = _get_partner_id(args)
    llm_backend = getattr(args, "llm_backend", None)
    if getattr(args, "use_llm_live_openai", False):
        llm_backend = "openai_live"
    if llm_backend == "openai_live" and not os.environ.get("OPENAI_API_KEY"):
        get_console().error(
            "OPENAI_API_KEY is required for --llm-backend openai_live. Reason code: OPENAI_API_KEY_MISSING"
        )
        return 1
    if llm_backend == "anthropic_live" and not os.environ.get("ANTHROPIC_API_KEY"):
        get_console().error(
            "ANTHROPIC_API_KEY is required for --llm-backend anthropic_live. Reason code: ANTHROPIC_API_KEY_MISSING"
        )
        return 1
    llm_agents_str = getattr(args, "llm_agents", "ops_0") or "ops_0"
    llm_agents = [a.strip() for a in llm_agents_str.split(",") if a.strip()]
    pipeline_mode = getattr(args, "pipeline_mode", None)
    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()
    scale_config_override = None
    if getattr(args, "scale", None) and args.task in (
        "coord_scale",
        "coord_risk",
    ):
        from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id

        try:
            scale_config_override = load_scale_config_by_id(root, args.scale)
        except (KeyError, FileNotFoundError, ValueError) as e:
            get_console().error(f"Invalid --scale {args.scale!r}: {e}")
            return 1
    metrics_aggregator_id = getattr(args, "metrics_aggregator_id", None)
    domain_id = getattr(args, "domain_id", None)
    out_path = Path(args.out)
    if not args.out or not str(args.out).strip():
        get_console().error("run-benchmark requires a non-empty --out path (e.g. --out results.json).")
        return 1
    resume_from = getattr(args, "resume_from", None)
    checkpoint_every = getattr(args, "checkpoint_every", None)
    if checkpoint_every is not None and (checkpoint_every < 1 or not getattr(args, "log", None)):
        if checkpoint_every < 1:
            get_console().error("--checkpoint-every must be >= 1.")
        else:
            get_console().error("--checkpoint-every requires --log so checkpoints can be written to the run directory.")
        return 1
    injection_id = getattr(args, "injection", None)
    _warn_reserved_injection(injection_id)
    con = get_console()

    def _progress_cb(current: int, total: int, _metrics: Any) -> None:
        con.progress(f"Episode {current}/{total}")

    try:
        _run(
            task_name=args.task,
            num_episodes=args.episodes,
            base_seed=args.seed,
            out_path=out_path,
            repo_root=root,
            log_path=Path(args.log) if getattr(args, "log", None) else None,
            partner_id=partner_id,
            llm_backend=llm_backend,
            llm_agents=llm_agents,
            llm_output_mode=getattr(args, "llm_output_mode", "json_schema"),
            llm_model=getattr(args, "llm_model", None),
            timing_mode=getattr(args, "timing", None),
            coord_method=getattr(args, "coord_method", None),
            injection_id=injection_id,
            scale_config_override=scale_config_override,
            pipeline_mode=pipeline_mode,
            allow_network=allow_network,
            metrics_aggregator_id=metrics_aggregator_id,
            domain_id=domain_id,
            coord_fixtures_path=getattr(args, "coord_fixtures_path", None),
            record_coord_fixtures_path=getattr(args, "record_coord_fixtures_path", None),
            coord_planner_backend=getattr(args, "coord_planner_backend", None),
            coord_bidder_backend=getattr(args, "coord_bidder_backend", None),
            coord_repair_backend=getattr(args, "coord_repair_backend", None),
            coord_detector_backend=getattr(args, "coord_detector_backend", None),
            progress_callback=_progress_cb,
            coord_planner_model=getattr(args, "coord_planner_model", None),
            coord_bidder_model=getattr(args, "coord_bidder_model", None),
            coord_repair_model=getattr(args, "coord_repair_model", None),
            coord_detector_model=getattr(args, "coord_detector_model", None),
            agent_driven=getattr(args, "agent_driven", False),
            multi_agentic=getattr(args, "multi_agentic", False),
            resume_from=resume_from,
            checkpoint_every_n_episodes=checkpoint_every,
            log_step_interval=getattr(args, "log_step_interval", 0) or None,
            checkpoint_every_n_steps=getattr(args, "checkpoint_every_steps", 0) or None,
            always_record_step_timing=getattr(args, "always_step_timing", False),
        )
    except ValueError as e:
        err = str(e)
        if "Unknown task" in err or "task" in err.lower():
            from labtrust_gym.benchmarks.tasks import list_tasks

            known = list_tasks()
            get_console().error(f"Task {args.task!r} not found. Known tasks: {', '.join(known)}")
        else:
            get_console().error(f"run-benchmark failed: {e}")
        return 1
    get_console().write_plain(f"Wrote {args.out}")
    if getattr(args, "log", None):
        get_console().info(f"Episode log {args.log}")
    if partner_id:
        get_console().info(f"Partner {partner_id!r}")
    return 0


def _run_benchmark_llm_live_eval(args: argparse.Namespace) -> int:
    """Run llm_live_eval profile: adversarial_disruption, insider_key_misuse, coord_risk with llm_live, allow-network, LLM_TRACE bundle."""
    get_console().info("Running run-benchmark (llm_live_eval profile).")
    from labtrust_gym.benchmarks.llm_trace import LLMTraceCollector
    from labtrust_gym.benchmarks.runner import run_benchmark

    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()
    if not allow_network:
        get_console().error(
            "llm_live_eval profile requires --allow-network (or LABTRUST_ALLOW_NETWORK=1). Refusing to run."
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
        ("adversarial_disruption", None),
        ("insider_key_misuse", None),
        ("coord_risk", "kernel_centralized_edf"),
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
            metrics_aggregator_id=getattr(args, "metrics_aggregator_id", None),
        )
        get_console().write_plain(f"Wrote {task_out}")

    trace_dir = out_path / "LLM_TRACE"
    collector.write_to_dir(trace_dir)
    get_console().write_plain(f"LLM trace written to {trace_dir}")

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
    get_console().info(f"Metadata (non_deterministic=true) written to {out_path / 'metadata.json'}")
    return 0


def _run_make_plots(args: argparse.Namespace) -> int:
    """Generate plots and data tables from study run."""
    get_console().info("Running make-plots.")
    from labtrust_gym.studies.plots import make_plots

    root = get_repo_root()
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    make_plots(run_dir, theme=getattr(args, "theme", "light"))
    fig_dir = run_dir / "figures"
    get_console().write_plain(f"Figures and data tables written to {fig_dir}")
    get_console().info(f"  Read {fig_dir / 'RUN_REPORT.md'} for metric definitions and data summary.")
    get_console().info(f"  Read {run_dir / 'RUN_SUMMARY.md'} for run context and output layout.")
    return 0


def _run_export_receipts(args: argparse.Namespace) -> int:
    """Export receipts and evidence bundle from episode log."""
    get_console().info("Running export-receipts.")
    from labtrust_gym.export.receipts import export_receipts

    root = get_repo_root()
    run_path = Path(args.run)
    if not run_path.is_absolute():
        run_path = root / run_path
    if not run_path.exists():
        get_console().error(f"Episode log not found: {run_path}")
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
    get_console().write_plain(f"Evidence bundle written to {bundle_dir}")
    return 0


def _run_verify_bundle(args: argparse.Namespace) -> int:
    """Verify a single EvidenceBundle.v0.1: manifest integrity, schema, hashchain, invariant trace."""
    get_console().info("Running verify-bundle.")
    from labtrust_gym.export.verify import verify_bundle

    root = get_repo_root()
    bundle_path = Path(args.bundle)
    if not bundle_path.is_absolute():
        bundle_path = root / bundle_path
    if not bundle_path.is_dir():
        get_console().error(f"Bundle not found or not a directory: {bundle_path}")
        return 1
    allow_extra = getattr(args, "allow_extra_files", False)
    strict_fingerprints = getattr(args, "strict_fingerprints", False)
    passed, report, errors = verify_bundle(
        bundle_path,
        policy_root=root,
        allow_extra_files=allow_extra,
        strict_fingerprints=strict_fingerprints,
    )
    get_console().write_plain(report)
    if errors:
        for e in errors:
            get_console().error(str(e))
    return 0 if passed else 1


def _run_verify_release(args: argparse.Namespace) -> int:
    """Verify all EvidenceBundle.v0.1 dirs under a release; exit non-zero if any fail."""
    get_console().info("Running verify-release.")
    from labtrust_gym.export.verify import discover_evidence_bundles, verify_release

    root = get_repo_root()
    release_path = Path(args.release_dir)
    if not release_path.is_absolute():
        release_path = root / release_path
    if not release_path.is_dir():
        get_console().error(f"Release directory not found or not a directory: {release_path}")
        return 1
    bundles = discover_evidence_bundles(release_path)
    if not bundles:
        get_console().error(f"No EvidenceBundle.v0.1 found under {release_path / 'receipts'}")
        return 1
    allow_extra = getattr(args, "allow_extra_files", False)
    quiet = getattr(args, "quiet", False)
    strict_fingerprints = getattr(args, "strict_fingerprints", False)
    all_passed, results, release_errors = verify_release(
        release_path,
        policy_root=root,
        allow_extra_files=allow_extra,
        quiet=quiet,
        strict_fingerprints=strict_fingerprints,
    )
    con = get_console()
    if release_errors:
        for e in release_errors:
            con.error(f"  Release: {e}")
    n = len(results)
    use_table = not quiet and results and con.verbosity >= Verbosity.NORMAL
    if use_table:
        table_rows = []
        for bundle_path, passed, _report, _errs in results:
            rel = bundle_path.relative_to(release_path) if bundle_path.is_relative_to(release_path) else bundle_path
            status = "PASS" if passed else "FAIL"
            table_rows.append([str(rel), status])
        if table_rows:
            con.table(["Bundle", "Status"], table_rows, title="verify-release")
    for bundle_path, passed, report, errors in results:
        rel = bundle_path.relative_to(release_path) if bundle_path.is_relative_to(release_path) else bundle_path
        status = "PASS" if passed else "FAIL"
        if not use_table:
            con.write_plain(f"  {rel}: {status}")
        if not quiet and not passed and errors:
            for e in errors[:3]:
                con.error(f"    {e}")
            if len(errors) > 3:
                con.error(f"    ... and {len(errors) - 3} more")
        if quiet and not passed:
            break
    total = len(bundles)
    summary = f"verify-release: {n} bundle(s) checked, {'all passed' if all_passed else 'at least one failed'}."
    if not quiet and n < total:
        summary += f" (stopped after first failure; {total - n} remaining)"
    if release_errors:
        summary += f"; {len(release_errors)} release-level error(s)"
    con.write_plain(summary)
    return 0 if all_passed else 1


def _run_build_release_manifest(args: argparse.Namespace) -> int:
    """Build RELEASE_MANIFEST.v0.1.json in release dir with hashes of key artifacts."""
    get_console().info("Running build-release-manifest.")
    from labtrust_gym.export.verify import build_release_manifest

    root = get_repo_root()
    release_path = Path(args.release_dir)
    if not release_path.is_absolute():
        release_path = root / release_path
    if not release_path.is_dir():
        get_console().error(f"Release directory not found or not a directory: {release_path}")
        return 1
    out_path = build_release_manifest(release_path, policy_root=root)
    get_console().write_plain(f"Wrote {out_path}")
    return 0


def _run_check_security_gate(args: argparse.Namespace) -> int:
    """Check pack_gate.md under --run; exit 0 if all cells PASS or not_supported, else exit 1."""
    get_console().info("Running check-security-gate.")
    from labtrust_gym.studies.coordination_decision_builder import check_security_gate

    root = get_repo_root()
    run_path = Path(args.run)
    if not run_path.is_absolute():
        run_path = root / run_path
    if not run_path.is_dir():
        get_console().error(f"Run directory not found: {run_path}")
        return 1
    passed, failed_cells = check_security_gate(run_path)
    if passed:
        get_console().write_plain("Security gate: PASS (no FAIL cells in pack_gate.md).")
        return 0
    get_console().error("Security gate: FAIL.")
    for c in failed_cells:
        get_console().error(f"  {c.get('scale_id')} / {c.get('method_id')} / {c.get('injection_id')}")
    return 1


def _run_ui_export(args: argparse.Namespace) -> int:
    """Export UI-ready zip (index, events, receipts_index, reason_codes) from run dir."""
    get_console().info("Running ui-export.")
    from labtrust_gym.export.ui_export import export_ui_bundle

    root = get_repo_root()
    run_path = Path(args.run)
    if not run_path.is_absolute():
        run_path = root / run_path
    if not run_path.is_dir():
        get_console().error(f"Run directory not found: {run_path}")
        return 1
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    try:
        export_ui_bundle(run_path, out_path, repo_root=root)
        get_console().write_plain(f"UI bundle written to {out_path}")
        return 0
    except (ValueError, FileNotFoundError) as e:
        get_console().error(f"ui-export failed: {e}")
        return 1


def _run_build_episode_bundle(args: argparse.Namespace) -> int:
    """Build episode_bundle.json from run dir for the simulation viewer."""
    get_console().info("Running build-episode-bundle.")
    from labtrust_gym.export.episode_bundle import (
        build_bundle_from_run_dir,
        write_bundle,
    )

    root = get_repo_root()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    if not run_dir.is_dir():
        get_console().error(f"Run directory not found: {run_dir}")
        return 1
    out_path = Path(args.out) if args.out else run_dir / "episode_bundle.json"
    if not out_path.is_absolute():
        out_path = root / out_path
    if out_path.is_dir():
        out_path = out_path / "episode_bundle.json"
    try:
        bundle = build_bundle_from_run_dir(run_dir)
        write_bundle(bundle, out_path)
        get_console().write_plain(f"Wrote {out_path}")
        return 0
    except FileNotFoundError as e:
        get_console().error(f"Error: {e}")
        return 1


def _run_build_risk_register_bundle(args: argparse.Namespace) -> int:
    """Build RiskRegisterBundle.v0.1 from policy and optional run dirs."""
    get_console().info("Running build-risk-register-bundle.")
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
        get_console().write_plain(f"Risk register bundle written to {out_path}")
        return 0
    except (ValueError, FileNotFoundError) as e:
        get_console().error(f"build-risk-register-bundle failed: {e}")
        return 1


def _run_export_risk_register(args: argparse.Namespace) -> int:
    """Export RiskRegisterBundle.v0.1 into --out dir; optional --runs and --include-official-pack."""
    get_console().info("Running export-risk-register.")
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
    partner_id = getattr(args, "partner", None)
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
            partner_id=partner_id,
            include_generated_at=getattr(args, "include_generated_at", False),
            include_git_hash=True,
            validate=not getattr(args, "no_validate", False),
            inject_ui_export=getattr(args, "inject_ui_export", False),
        )
        get_console().write_plain(f"{RISK_REGISTER_BUNDLE_FILENAME} written to {out_path}")
        return 0
    except (ValueError, FileNotFoundError) as e:
        get_console().error(f"export-risk-register failed: {e}")
        return 1


def _run_validate_coverage(args: argparse.Namespace) -> int:
    """Validate risk register bundle coverage; with --strict, fail if any required risk has missing evidence."""
    get_console().info("Running validate-coverage.")
    import json

    from labtrust_gym.export.risk_register_bundle import (
        RISK_REGISTER_BUNDLE_FILENAME,
        check_risk_register_coverage,
    )

    root = get_repo_root()
    bundle_path = getattr(args, "bundle", None)
    if bundle_path is not None:
        bundle_path = Path(bundle_path)
        if not bundle_path.is_absolute():
            bundle_path = root / bundle_path
    else:
        out_dir = getattr(args, "out", None)
        if out_dir is None:
            out_dir = root / "risk_register_out"
        else:
            out_dir = Path(out_dir)
            if not out_dir.is_absolute():
                out_dir = root / out_dir
        bundle_path = out_dir / RISK_REGISTER_BUNDLE_FILENAME
    if not bundle_path.exists():
        get_console().error(f"Bundle not found: {bundle_path}")
        return 1
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except Exception as e:
        get_console().error(f"Failed to load bundle: {e}")
        return 1
    waived_cells = None
    if getattr(args, "strict", False):
        from labtrust_gym.export.risk_register_bundle import load_waivers

        waived_cells = load_waivers(root)
    passed, missing_list = check_risk_register_coverage(bundle, root, waived_cells=waived_cells)
    if passed:
        if getattr(args, "strict", False):
            get_console().write_plain("Coverage OK: all required_bench cells evidenced or waived.")
        return 0
    if getattr(args, "strict", False):
        get_console().error("Coverage FAIL: required risks with missing evidence (method_id, risk_id):")
        for mid, rid in sorted(missing_list):
            get_console().error(f"  {mid} {rid}")
        return 1
    get_console().write_plain(
        f"Coverage: {len(missing_list)} required cell(s) with evidence gaps (run with --strict to fail)."
    )
    return 0


def _run_show_method_risk_matrix(args: argparse.Namespace) -> int:
    """Print or export method x risk matrix (table/csv/markdown)."""
    get_console().info("Running show-method-risk-matrix.")
    from labtrust_gym.policy.coordination import load_method_risk_matrix
    from labtrust_gym.studies.matrix_view import format_method_risk_matrix

    root = Path(args.policy_root) if getattr(args, "policy_root", None) else get_repo_root()
    if not root.is_absolute():
        root = get_repo_root() / root
    matrix_path = root / "policy" / "coordination" / "method_risk_matrix.v0.1.yaml"
    if not matrix_path.is_file():
        get_console().error(f"Matrix not found: {matrix_path}")
        return 1
    try:
        matrix = load_method_risk_matrix(matrix_path)
    except Exception as e:
        get_console().error(f"Failed to load matrix: {e}")
        return 1
    out_fmt = getattr(args, "format", "table")
    text = format_method_risk_matrix(matrix, output_format=out_fmt)
    out_path = getattr(args, "out", None)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        get_console().write_plain(f"Wrote {out_path}")
    else:
        print(text)
    return 0


def _run_show_pack_matrix(args: argparse.Namespace) -> int:
    """Print or export pack matrix (method x scale x injection) with scale taxonomy."""
    get_console().info("Running show-pack-matrix.")
    from labtrust_gym.studies.matrix_view import format_pack_matrix

    root = Path(args.policy_root) if getattr(args, "policy_root", None) else get_repo_root()
    if not root.is_absolute():
        root = get_repo_root() / root
    preset = getattr(args, "matrix_preset", None)
    out_fmt = getattr(args, "format", "table")
    text = format_pack_matrix(
        root,
        matrix_preset=preset,
        output_format=out_fmt,
        include_scale_taxonomy=True,
    )
    out_path = getattr(args, "out", None)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        get_console().write_plain(f"Wrote {out_path}")
    else:
        print(text)
    return 0


def _run_show_pack_results(args: argparse.Namespace) -> int:
    """Show result matrix from a completed pack run (real results)."""
    get_console().info("Running show-pack-results.")
    from labtrust_gym.studies.matrix_view import format_pack_results_from_run

    run_dir = Path(getattr(args, "run", ""))
    if not run_dir.is_absolute():
        run_dir = get_repo_root() / run_dir
    if not run_dir.is_dir():
        get_console().error(f"Run directory not found: {run_dir}")
        return 1
    out_fmt = getattr(args, "format", "markdown")
    text = format_pack_results_from_run(run_dir, output_format=out_fmt)
    out_path = getattr(args, "out", None)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
        get_console().write_plain(f"Wrote {out_path}")
    else:
        print(text)
    return 0


def _run_export_fhir(args: argparse.Namespace) -> int:
    """Export FHIR R4 Bundle from receipts directory."""
    get_console().info("Running export-fhir.")
    from labtrust_gym.export.fhir_r4 import export_fhir

    root = get_repo_root()
    receipts_dir = Path(args.receipts)
    if not receipts_dir.is_absolute():
        receipts_dir = root / receipts_dir
    if not receipts_dir.exists():
        get_console().error(f"Receipts directory not found: {receipts_dir}")
        return 1
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = getattr(args, "filename", "fhir_bundle.json")
    out_path = export_fhir(receipts_dir, out_dir, out_filename=filename)
    get_console().write_plain(f"FHIR bundle written to {out_path}")
    return 0


def _run_validate_fhir(args: argparse.Namespace) -> int:
    """Validate FHIR Bundle coded elements against terminology value set."""
    get_console().info("Running validate-fhir.")
    import json

    from labtrust_gym.export.fhir_terminology import validate_bundle_against_value_sets

    root = get_repo_root()
    bundle_path = Path(args.bundle)
    if not bundle_path.is_absolute():
        bundle_path = root / bundle_path
    if not bundle_path.exists():
        get_console().error(f"Bundle file not found: {bundle_path}")
        return 1
    terminology_path = Path(args.terminology)
    if not terminology_path.is_absolute():
        terminology_path = root / terminology_path
    if not terminology_path.exists():
        get_console().error(f"Terminology file not found: {terminology_path}")
        return 1
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        get_console().error(f"Failed to load bundle: {e}")
        return 1
    try:
        term_data = json.loads(terminology_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        get_console().error(f"Failed to load terminology: {e}")
        return 1
    value_sets = term_data.get("value_sets")
    if not isinstance(value_sets, dict):
        get_console().error("Terminology file must have 'value_sets' object (system URI -> list of codes)")
        return 1
    value_sets_normalized = {}
    for k, v in value_sets.items():
        if isinstance(v, list):
            value_sets_normalized[k] = [str(c) for c in v]
        else:
            value_sets_normalized[k] = []
    violations = validate_bundle_against_value_sets(bundle, value_sets_normalized)
    if violations:
        for v in violations:
            get_console().error(
                f"{v.get('resourceType')} {v.get('id')} {v.get('path')}: code {v.get('code')!r} not in value set for system {v.get('system')!r}"
            )
        if getattr(args, "strict", False):
            return 1
    else:
        get_console().write_plain("validate-fhir: no terminology violations")
    return 0


def _run_reproduce(args: argparse.Namespace) -> int:
    """Run reproduce: minimal study sweep (throughput_sla, qc_cascade) + plots."""
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
    include_coordination_pack = getattr(args, "include_coordination_pack", False)
    try:
        result = run_package_release(
            profile=args.profile,
            out_dir=out_dir,
            repo_root=root,
            seed_base=seed_base,
            include_repro_dir=include_repro,
            pipeline_mode=pipeline_mode,
            allow_network=allow_network,
            include_coordination_pack=include_coordination_pack,
        )
        get_console().write_plain(f"Release artifact written to {result}")
        get_console().info("  MANIFEST.v0.1.json, BENCHMARK_CARD.md, metadata.json")
        get_console().info("  results.json, plots/, tables/, receipts/, fhir/")
        return 0
    except Exception as e:
        get_console().error(f"package-release failed: {e}")
        return 1


def _run_security_suite(args: argparse.Namespace) -> int:
    """Run security attack suite and emit SECURITY/attack_results.json + packet."""
    from labtrust_gym.benchmarks.securitization import emit_securitization_packet
    from labtrust_gym.benchmarks.security_runner import run_suite_and_emit

    get_console().info("Running run-security-suite (attack suite -> SECURITY/).")
    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    smoke_only = not getattr(args, "full", False)
    seed = getattr(args, "seed", 42)
    timeout_s = getattr(args, "timeout", 120)
    llm_attacker = getattr(args, "llm_attacker", False)
    allow_network = getattr(args, "allow_network", False) or bool(os.environ.get("LABTRUST_ALLOW_NETWORK"))
    llm_backend = getattr(args, "llm_backend", None)
    llm_model = getattr(args, "llm_model", None)
    if llm_attacker and (not allow_network or not llm_backend):
        get_console().warning(
            "--llm-attacker requires --allow-network and --llm-backend; skipping LLM-attacker attacks."
        )
        llm_attacker = False
    if llm_attacker and allow_network:
        get_console().info(
            "WILL MAKE NETWORK CALLS: LLM-attacker mode enabled; live LLM will generate adversarial payloads."
        )
        from labtrust_gym.pipeline import set_pipeline_config

        set_pipeline_config(
            pipeline_mode="llm_live",
            allow_network=True,
            llm_backend_id=llm_backend,
        )
    provider_id = getattr(args, "security_suite_provider_id", None)
    security_suite_path = getattr(args, "security_suite_path", None)
    max_payload_chars = getattr(args, "llm_attacker_max_chars", 2000)
    llm_attacker_rounds = getattr(args, "llm_attacker_rounds", None)
    skip_system_level = getattr(args, "skip_system_level", False)
    con = get_console()

    def _security_progress(current: int, total: int, attack_id: str) -> None:
        con.progress(f"Security test {current}/{total}: {attack_id}")

    try:
        results = run_suite_and_emit(
            policy_root=root,
            out_dir=out_dir,
            repo_root=root,
            smoke_only=smoke_only,
            seed=seed,
            timeout_s=timeout_s,
            metadata={
                "seed": seed,
                "smoke_only": smoke_only,
                "timeout_s": timeout_s,
                "git_sha": _git_sha(),
            },
            llm_attacker=llm_attacker,
            allow_network=allow_network,
            llm_backend=llm_backend,
            llm_model=llm_model,
            provider_id=provider_id,
            security_suite_path=security_suite_path,
            max_payload_chars=max_payload_chars,
            skip_system_level=skip_system_level,
            llm_attacker_rounds=llm_attacker_rounds,
            agent_driven_mode=getattr(args, "agent_driven_mode", None),
            use_full_driver_loop=getattr(args, "use_full_driver_loop", False),
            use_mock_env=getattr(args, "use_mock_env", False),
            progress_callback=_security_progress,
        )
        emit_securitization_packet(root, out_dir)
        if any(r.get("llm_attacker") for r in results):
            model_ids = list(
                dict.fromkeys(r.get("model_id") for r in results if r.get("llm_attacker") and r.get("model_id"))
            )
            note_path = out_dir / "SECURITY" / "llm_attacker_note.txt"
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(
                "LLM attacker (live) run. Model IDs: " + ", ".join(model_ids or ["unknown"]),
                encoding="utf-8",
            )
        passed = sum(1 for r in results if r.get("passed"))
        get_console().write_plain(f"Security suite: {passed}/{len(results)} passed")
        get_console().write_plain(f"SECURITY/ written to {out_dir / 'SECURITY'}")
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
                get_console().info("Hint: install into the same Python that runs labtrust (copy-paste):")
                get_console().info(f"  {ps_cmd}")
                get_console().info("  (PowerShell: use as-is. Cmd: omit the leading & )")
                ensurepip_cmd = f'& "{exe}" -m ensurepip --upgrade'
                get_console().info(f"  (If 'No module named pip', run first: {ensurepip_cmd})")
        return 0 if passed == len(results) else 1
    except Exception as e:
        get_console().error(f"run-security-suite failed: {e}")
        return 1


def _run_safety_case(args: argparse.Namespace) -> int:
    """Generate safety case to SAFETY_CASE/safety_case.json and safety_case.md."""
    get_console().info("Running safety-case.")
    from labtrust_gym.security.safety_case import emit_safety_case

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    provider_id = getattr(args, "safety_case_provider_id", None)
    claims_path = getattr(args, "safety_claims_path", None)
    try:
        emit_safety_case(policy_root=root, out_dir=out_dir, provider_id=provider_id, claims_path=claims_path)
        safety_dir = out_dir / "SAFETY_CASE"
        get_console().write_plain(f"SAFETY_CASE/ written to {safety_dir}")
        return 0
    except Exception as e:
        get_console().error(f"safety-case failed: {e}")
        return 1


def _run_deps_inventory(args: argparse.Namespace) -> int:
    """Write runtime dependency inventory to <out>/SECURITY/deps_inventory_runtime.json."""
    get_console().info("Running deps-inventory.")
    from labtrust_gym.security.deps_inventory import write_deps_inventory_runtime

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = write_deps_inventory_runtime(out_dir, repo_root=root)
    get_console().write_plain(f"Wrote {out_path}")
    return 0


def _run_audit_selfcheck(args: argparse.Namespace) -> int:
    """Run Phase A audit checks and doctor-style env checks; write AUDIT_SELF_CHECK.json."""
    get_console().info("Running audit-selfcheck.")
    import subprocess
    import time

    from labtrust_gym.export.risk_register_bundle import (
        RISK_REGISTER_BUNDLE_FILENAME,
        export_risk_register,
    )

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Doctor-style checks (Python path, venv, extras, filesystem, policy)
    from labtrust_gym.cli.audit_checks import run_doctor_checks

    doctor_checks, doctor_pass = run_doctor_checks(root)
    all_pass = doctor_pass

    risk_register_out = out_dir / "risk_register_out"
    steps: list[dict[str, Any]] = []

    # 1. no_placeholders
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            [sys.executable, str(root / "tools" / "no_placeholders.py"), str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed = r.returncode == 0
    except Exception:
        passed = False
    steps.append({"name": "no_placeholders", "pass": passed, "duration_s": round(time.perf_counter() - t0, 3)})
    if not passed:
        all_pass = False

    # 2. validate-policy (default partner)
    t0 = time.perf_counter()
    errs = validate_policy(root, partner_id=None)
    passed = len(errs) == 0
    steps.append({"name": "validate_policy", "pass": passed, "duration_s": round(time.perf_counter() - t0, 3)})
    if not passed:
        all_pass = False

    # 3. validate-policy --partner hsl_like
    t0 = time.perf_counter()
    errs_partner = validate_policy(root, partner_id="hsl_like")
    passed = len(errs_partner) == 0
    steps.append({"name": "validate_policy_hsl_like", "pass": passed, "duration_s": round(time.perf_counter() - t0, 3)})
    if not passed:
        all_pass = False

    # 4. export-risk-register --out <out>/risk_register_out --runs tests/fixtures/ui_fixtures
    t0 = time.perf_counter()
    try:
        export_risk_register(
            repo_root=root,
            out_dir=risk_register_out,
            run_specs=[str(root / "tests" / "fixtures" / "ui_fixtures")],
            include_official_pack_dir=None,
            partner_id=None,
            include_generated_at=False,
            include_git_hash=True,
            validate=True,
            inject_ui_export=False,
        )
        passed = True
    except (ValueError, FileNotFoundError):
        passed = False
    steps.append({"name": "export_risk_register", "pass": passed, "duration_s": round(time.perf_counter() - t0, 3)})
    if not passed:
        all_pass = False

    # 5. risk register contract gate (pytest)
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_risk_register_contract_gate.py", "-v", "--tb=short"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        passed = r.returncode == 0
    except Exception:
        passed = False
    steps.append(
        {"name": "risk_register_contract_gate", "pass": passed, "duration_s": round(time.perf_counter() - t0, 3)}
    )
    if not passed:
        all_pass = False

    bundle_path = risk_register_out / RISK_REGISTER_BUNDLE_FILENAME
    artifact_links: dict[str, str] = {}
    if bundle_path.is_file():
        artifact_links["risk_register_bundle"] = str(bundle_path)

    payload = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "python_version": sys.version.split()[0],
        "checks": doctor_checks,
        "steps": steps,
        "overall_pass": all_pass,
        "artifact_links": artifact_links,
    }
    out_json = out_dir / "AUDIT_SELF_CHECK.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    get_console().write_plain(f"Wrote {out_json}")
    return 0 if all_pass else 1


def _run_transparency_log(args: argparse.Namespace) -> int:
    """Build TRANSPARENCY_LOG/ from artifact dir (--in) into --out."""
    get_console().info("Running transparency-log.")
    from labtrust_gym.security.transparency import write_transparency_log

    root = get_repo_root()
    in_dir = Path(getattr(args, "in_dir", ""))
    if not in_dir.is_absolute():
        in_dir = root / in_dir
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    if not in_dir.is_dir():
        get_console().error(f"Input directory not found: {in_dir}")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir = write_transparency_log(in_dir, out_dir)
    get_console().write_plain(f"Wrote {log_dir} (log.json, root.txt, proofs/)")
    return 0


def _run_study(args: argparse.Namespace) -> int:
    """Run study from spec; write manifest, conditions.jsonl, results/, logs/."""
    get_console().info("Running study.")
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
    get_console().write_plain(f"Study written to {out_dir}")
    return 0


def _run_coordination_study(args: argparse.Namespace) -> int:
    """Run coordination study from spec; write cells/, summary/summary_coord.csv, summary/pareto.md."""
    get_console().info("Running coordination-study.")
    from labtrust_gym.studies.coordination_study_runner import run_coordination_study

    root = get_repo_root()
    profile_spec = getattr(args, "coordination_study_spec_path", None)
    if profile_spec is not None:
        spec_path = Path(profile_spec)
    else:
        spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    partner_id = getattr(args, "partner", None)
    if partner_id and profile_spec is None:
        overlay_spec = root / "policy" / "partners" / partner_id / "coordination" / "coordination_study_spec.v0.1.yaml"
        if overlay_spec.exists():
            spec_path = overlay_spec
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    llm_backend = getattr(args, "llm_backend", None)
    llm_model = getattr(args, "llm_model", None)
    emit_matrix = getattr(args, "emit_coordination_matrix", False)

    if emit_matrix:
        pipeline_mode = (
            "llm_live" if llm_backend in ("openai_live", "ollama_live") else (llm_backend or "deterministic")
        )
        if pipeline_mode != "llm_live":
            get_console().warning(
                "emit-coordination-matrix requires llm_live pipeline (--llm-backend openai_live or ollama_live). "
                f"This run uses pipeline_mode={pipeline_mode!r}. Matrix builder is llm_live-only; offline pipelines are out of scope."
            )
            return 1

    if llm_backend == "openai_live" and not os.environ.get("OPENAI_API_KEY"):
        get_console().error(
            "OPENAI_API_KEY is required for --llm-backend openai_live. Reason code: OPENAI_API_KEY_MISSING"
        )
        return 1
    run_coordination_study(spec_path, out_dir, repo_root=root, llm_backend=llm_backend, llm_model=llm_model)
    get_console().write_plain(f"Coordination study written to {out_dir}")

    if emit_matrix:
        from labtrust_gym.studies.coordination_matrix_builder import (
            build_coordination_matrix,
        )

        matrix_path = out_dir / COORDINATION_MATRIX_CANONICAL_FILENAME
        build_coordination_matrix(out_dir, matrix_path, policy_root=root, strict=True)
        get_console().write_plain(f"Coordination matrix written to {matrix_path}")

    return 0


def _run_coordination_security_pack(args: argparse.Namespace) -> int:
    """Run coordination security pack; write pack_results/, pack_summary.csv, pack_gate.md."""
    get_console().info("Running coordination-security-pack.")
    from labtrust_gym.studies.coordination_security_pack import (
        run_coordination_security_pack,
    )

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    seed_base = getattr(args, "seed", 42)
    methods_from = getattr(args, "methods_from", "fixed")
    injections_from = getattr(args, "injections_from", "fixed")
    scales_from = getattr(args, "scales_from", "default")
    matrix_preset = getattr(args, "matrix_preset", None)
    scale_ids = getattr(args, "scale_ids", None)
    partner_id = _get_partner_id(args)
    workers = max(1, int(getattr(args, "workers", 1)))
    llm_backend = getattr(args, "llm_backend", None)
    allow_network = getattr(args, "allow_network", False)
    run_coordination_security_pack(
        out_dir=out_dir,
        repo_root=root,
        seed_base=seed_base,
        methods_from=methods_from,
        injections_from=injections_from,
        scales_from=scales_from,
        matrix_preset=matrix_preset,
        scale_ids_filter=scale_ids,
        partner_id=partner_id,
        workers=workers,
        llm_backend=llm_backend,
        allow_network=allow_network,
    )
    get_console().write_plain(f"Coordination security pack written to {out_dir}")
    return 0


# Canonical filename for coordination matrix output when --out is a directory (contract gate / Prompt 0).
COORDINATION_MATRIX_CANONICAL_FILENAME = "coordination_matrix.v0.1.json"


def _run_build_coordination_matrix(args: argparse.Namespace) -> int:
    """Build CoordinationMatrix v0.1 from llm_live run dir; print summary."""
    get_console().info("Running build-coordination-matrix.")
    from labtrust_gym.studies.coordination_matrix_builder import (
        build_coordination_matrix,
    )

    root = get_repo_root()
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    out_arg = Path(args.out)
    if not out_arg.is_absolute():
        out_arg = root / out_arg
    if out_arg.is_dir() or out_arg.suffix.lower() != ".json":
        out_path = out_arg / COORDINATION_MATRIX_CANONICAL_FILENAME
    else:
        out_path = out_arg
    out_path.parent.mkdir(parents=True, exist_ok=True)
    policy_root = getattr(args, "policy_root", None)
    if policy_root is not None:
        policy_root = Path(policy_root)
        if not policy_root.is_absolute():
            policy_root = root / policy_root
    strict = not getattr(args, "no_strict", False)
    matrix_mode = getattr(args, "matrix_mode", "llm_live")
    matrix = build_coordination_matrix(
        run_dir,
        out_path,
        policy_root=policy_root,
        strict=strict,
        matrix_mode=matrix_mode,
    )
    rows = matrix.get("rows") or []
    scales = matrix.get("scales") or []
    n_scales = len(scales)
    method_ids = sorted({r["method_id"] for r in rows})
    n_methods = len(method_ids)
    alpha = 0.6
    method_scores: dict[str, list[float]] = {}
    for r in rows:
        if not r.get("feasible", {}).get("overall", True):
            continue
        mid = r["method_id"]
        s = r.get("scores") or {}
        cq = float(s.get("cq_score", 0.0))
        ar = float(s.get("ar_score", 0.0))
        overall = alpha * cq + (1.0 - alpha) * ar
        method_scores.setdefault(mid, []).append(overall)
    global_avg = {mid: (sum(s) / len(s)) if s else 0.0 for mid, s in method_scores.items()}
    top3 = sorted(global_avg.items(), key=lambda x: -x[1])[:3]
    get_console().info(f"Scales: {n_scales}")
    get_console().info(f"Methods: {n_methods}")
    if top3:
        get_console().info("Top-3 methods by global overall score:")
        for i, (mid, score) in enumerate(top3, 1):
            get_console().info(f"  {i}. {mid}: {score:.4f}")
    get_console().info("llm_live-only enforced.")
    get_console().write_plain(f"Matrix written to {out_path}")
    return 0


def _run_recommend_coordination_method(args: argparse.Namespace) -> int:
    """Produce COORDINATION_DECISION.v0.1.json and COORDINATION_DECISION.md from run dir."""
    get_console().info("Running recommend-coordination-method.")
    from labtrust_gym.studies.coordination_decision_builder import (
        run_recommend_coordination_method,
    )

    root = get_repo_root()
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    policy_root = getattr(args, "policy_root", None)
    if policy_root is not None:
        policy_root = Path(policy_root)
        if not policy_root.is_absolute():
            policy_root = root / policy_root
    else:
        policy_root = root
    result = run_recommend_coordination_method(run_dir=run_dir, out_dir=out_dir, policy_root=policy_root)
    decision = result["decision"]
    get_console().write_plain(f"Verdict: {decision.get('verdict')}")
    for sd in decision.get("scale_decisions") or []:
        chosen = sd.get("chosen_method_id")
        get_console().info(f"  {sd.get('scale_id')}: {chosen or '(no admissible method)'}")
    get_console().info(f"JSON: {result['json_path']}")
    get_console().info(f"MD:   {result['md_path']}")
    return 0


def _run_summarize_coordination(args: argparse.Namespace) -> int:
    """Aggregate coordination results: SOTA leaderboard + method-class comparison from summary_coord.csv."""
    get_console().info("Running summarize-coordination.")
    from labtrust_gym.studies.coordination_summarizer import run_summarize

    root = get_repo_root()
    in_dir = Path(getattr(args, "in_dir", ""))
    out_dir = Path(getattr(args, "out_dir", ""))
    if not in_dir.is_absolute():
        in_dir = root / in_dir
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    run_summarize(in_dir=in_dir, out_dir=out_dir, repo_root=root)
    get_console().write_plain(
        f"Wrote summary/sota_leaderboard.csv, sota_leaderboard.md, method_class_comparison.csv, method_class_comparison.md under {out_dir}"
    )
    return 0


def _run_build_lab_coordination_report(args: argparse.Namespace) -> int:
    """Build lab coordination report: summarize + recommend + LAB_COORDINATION_REPORT.md."""
    get_console().info("Running build-lab-coordination-report.")
    from labtrust_gym.studies.lab_report_builder import build_lab_coordination_report

    root = get_repo_root()
    pack_dir = Path(args.pack_dir)
    if not pack_dir.is_absolute():
        pack_dir = root / pack_dir
    out_dir = getattr(args, "out", None)
    if out_dir is not None:
        out_dir = Path(out_dir)
        if not out_dir.is_absolute():
            out_dir = root / out_dir
    else:
        out_dir = None
    policy_root = getattr(args, "policy_root", None)
    if policy_root is not None:
        policy_root = Path(policy_root)
        if not policy_root.is_absolute():
            policy_root = root / policy_root
    else:
        policy_root = root
    matrix_preset = getattr(args, "matrix_preset", None)
    include_matrix = getattr(args, "include_matrix", False)
    partner_id = _get_partner_id(args)
    report_path = build_lab_coordination_report(
        pack_dir=pack_dir,
        out_dir=out_dir,
        policy_root=policy_root,
        matrix_preset_name=matrix_preset,
        include_matrix=include_matrix,
        partner_id=partner_id,
    )
    get_console().write_plain(f"Lab coordination report written to {report_path}")
    return 0


def _run_forker_quickstart(args: argparse.Namespace) -> int:
    """One-command forker flow: validate, pack (fixed + critical), report, export risk register; print artifact paths."""
    get_console().info("Running forker-quickstart.")
    from labtrust_gym.export.risk_register_bundle import (
        RISK_REGISTER_BUNDLE_FILENAME,
        export_risk_register,
    )
    from labtrust_gym.studies.coordination_security_pack import run_coordination_security_pack
    from labtrust_gym.studies.lab_report_builder import build_lab_coordination_report

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    partner_id = _get_partner_id(args)

    if _run_validate_policy(root, partner_id) != 0:
        return 1

    pack_dir = out_dir / "pack"
    get_console().info("Running coordination security pack (fixed methods, critical injections)...")
    run_coordination_security_pack(
        out_dir=pack_dir,
        repo_root=root,
        seed_base=42,
        methods_from="fixed",
        injections_from="critical",
        partner_id=partner_id,
    )

    get_console().info("Building lab coordination report...")
    build_lab_coordination_report(
        pack_dir=pack_dir,
        out_dir=pack_dir,
        policy_root=root,
        partner_id=partner_id,
    )

    risk_out = out_dir / "risk_out"
    get_console().info("Exporting risk register...")
    export_risk_register(
        repo_root=root,
        out_dir=risk_out,
        run_specs=[str(pack_dir)],
        partner_id=partner_id,
    )

    decision_json = pack_dir / "COORDINATION_DECISION.v0.1.json"
    decision_md = pack_dir / "COORDINATION_DECISION.md"
    bundle_path = risk_out / RISK_REGISTER_BUNDLE_FILENAME
    get_console().success("Forker quickstart done.")
    get_console().info(f"  COORDINATION_DECISION (JSON): {decision_json}")
    get_console().info(f"  COORDINATION_DECISION (MD):   {decision_md}")
    get_console().info(f"  Risk register bundle:         {bundle_path}")
    return 0


def _run_live_orchestrator(args: argparse.Namespace) -> int:
    """Run live orchestrator: chosen method, run dir with matrix + decision + receipts + defense."""
    get_console().info("Running live-orchestrator.")
    from labtrust_gym.orchestrator.config import OrchestratorConfig
    from labtrust_gym.orchestrator.live import run_live_orchestrator

    root = get_repo_root()
    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    policy_root = getattr(args, "policy_root", None)
    if policy_root is not None:
        policy_root = Path(policy_root)
        if not policy_root.is_absolute():
            policy_root = root / policy_root
    else:
        policy_root = root
    injection_id = getattr(args, "injection", None)
    _warn_reserved_injection(injection_id)
    config = OrchestratorConfig(
        run_dir=run_dir,
        chosen_method_id=args.method,
        policy_root=policy_root,
        allow_network=getattr(args, "allow_network", False),
        scale_id=getattr(args, "scale", "small_smoke"),
        injection_id=injection_id,
        num_episodes=getattr(args, "episodes", 1),
        base_seed=getattr(args, "seed", 42),
        llm_backend=getattr(args, "llm_backend", "deterministic"),
        llm_model=getattr(args, "llm_model", None),
    )
    result = run_live_orchestrator(config)
    get_console().info(f"Run dir: {result['run_dir']}")
    get_console().info(f"Cell: {result['cell_id']}")
    get_console().info(f"Defense state: {result.get('defense_state', 'n/a')}")
    return 0


def _run_summarize_results(args: argparse.Namespace) -> int:
    """Load results.json from --in paths, aggregate, write summary.csv + summary.md to --out."""
    get_console().info("Running summarize-results.")
    from labtrust_gym.benchmarks.summarize import run_summarize

    root = get_repo_root()
    in_paths = [root / p if not Path(p).is_absolute() else Path(p) for p in args.in_paths]
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    basename = getattr(args, "basename", "summary")
    csv_path, md_path = run_summarize(in_paths, out_dir, out_basename=basename)
    get_console().write_plain(f"Wrote {csv_path}")
    get_console().write_plain(f"Wrote {md_path}")
    return 0


def _run_run_summary(args: argparse.Namespace) -> int:
    """Print one-line stats for a run directory (episodes, steps, violations, throughput)."""
    get_console().info("Running run-summary.")
    import json as _json

    from labtrust_gym.benchmarks.summarize import run_dir_stats

    root = get_repo_root()
    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    if not run_dir.is_dir():
        get_console().error(f"Not a directory: {run_dir}")
        return 1
    stats = run_dir_stats(run_dir)
    out_fmt = getattr(args, "format", "text")
    if out_fmt == "json":
        # Minimal dict for JSON (omit run_dir if desired; plan says one-line stats)
        out = {
            "num_episodes": stats["num_episodes"],
            "total_steps": stats["total_steps"],
            "violations_total": stats["violations_total"],
            "throughput_mean": stats["throughput_mean"],
        }
        if stats.get("task"):
            out["task"] = stats["task"]
        print(_json.dumps(out, indent=0))
    else:
        parts = [f"episodes={stats['num_episodes']}"]
        if stats.get("total_steps") is not None:
            parts.append(f"steps={stats['total_steps']}")
        if stats.get("violations_total") is not None:
            parts.append(f"violations={stats['violations_total']}")
        if stats.get("throughput_mean") is not None:
            parts.append(f"throughput={stats['throughput_mean']:.4f}")
        print(" ".join(parts))
    return 0


def _run_determinism_report(args: argparse.Namespace) -> int:
    """Run benchmark twice in fresh temp dirs; write determinism_report.md and .json; exit 1 if non-deterministic."""
    get_console().info("Running determinism-report.")
    from labtrust_gym.benchmarks.determinism_report import run_determinism_report

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    partner_id = _get_partner_id(args)
    timing = getattr(args, "timing", "explicit") or "explicit"
    injection_id = getattr(args, "injection", None)
    _warn_reserved_injection(injection_id)
    passed, report, _ = run_determinism_report(
        task_name=args.task,
        num_episodes=args.episodes,
        base_seed=args.seed,
        out_dir=out_dir,
        partner_id=partner_id,
        timing_mode=timing,
        repo_root=root,
        coord_method=getattr(args, "coord_method", None),
        pipeline_mode=getattr(args, "pipeline_mode", None),
        llm_backend=getattr(args, "llm_backend", None),
        injection_id=injection_id,
    )
    get_console().write_plain(f"Wrote {out_dir / 'determinism_report.json'}")
    get_console().write_plain(f"Wrote {out_dir / 'determinism_report.md'}")
    if passed:
        get_console().write_plain("Determinism check PASSED.")
        return 0
    for e in report.get("errors", []):
        get_console().error(str(e))
    return 1


def _run_generate_official_baselines(args: argparse.Namespace) -> int:
    """Regenerate official baseline results: run core tasks (from registry), write results/, summary.csv, summary.md, metadata.json."""
    get_console().info("Running generate-official-baselines.")
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
        get_console().error(f"Refusing to overwrite existing directory: {out_dir}. Use --force to overwrite.")
        return 1

    episodes = getattr(args, "episodes", 200)
    seed = getattr(args, "seed", 123)
    timing = getattr(args, "timing", "explicit") or "explicit"
    partner_id = _get_partner_id(args)
    git_sha = _git_sha()

    tasks_in_order, task_to_baseline_id, task_to_suffix = load_official_baseline_registry(root)
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
        suffix = task_to_suffix.get(task, task_to_baseline_id.get(task, "scripted_ops_v1").replace("_v1", ""))
        out_path = results_dir / f"{task}_{suffix}.json"
        get_console().info(f"Running {task} ({episodes} episodes, seed={seed}, timing={timing}) -> {out_path}")
        run_benchmark(
            task_name=task,
            num_episodes=episodes,
            base_seed=seed,
            out_path=out_path,
            repo_root=root,
            log_path=None,
            partner_id=partner_id,
            timing_mode=timing,
            metrics_aggregator_id=getattr(args, "metrics_aggregator_id", None),
        )
        if schema_path:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            errors = validate_results_v02(data, schema_path=schema_path)
            if errors:
                for e in errors:
                    get_console().error(f"Validation error {out_path}: {e}")
                return 1

    result_paths = [results_dir / f"{task}_{task_to_suffix[task]}.json" for task in tasks_in_order]
    csv_path, md_path = run_summarize(
        result_paths,
        out_dir,
        out_basename="summary",
    )
    get_console().write_plain(f"Wrote {csv_path}")
    get_console().write_plain(f"Wrote {md_path}")

    # Deterministic timestamp when seed provided (UTC epoch + seed seconds)
    if seed is not None:
        ts = (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=seed)).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    baseline_ids_used = list(dict.fromkeys(task_to_baseline_id[t] for t in tasks_in_order))
    metadata = {
        "version": "0.2",
        "baseline_version": "v0.2",
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
    get_console().write_plain(f"Wrote {metadata_path}")
    return 0


def _run_official_pack(args: argparse.Namespace) -> int:
    """Run official benchmark pack: baselines, SECURITY, SAFETY_CASE, TRANSPARENCY_LOG."""
    from labtrust_gym.benchmarks.official_pack import run_official_pack

    get_console().info("Running run-official-pack with baselines, SECURITY, SAFETY_CASE, TRANSPARENCY_LOG.")
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
    llm_backend = getattr(args, "llm_backend", None)
    include_coordination_pack = getattr(args, "include_coordination_pack", False)
    partner_id = getattr(args, "partner", None)
    metrics_aggregator_id = getattr(args, "metrics_aggregator_id", None)
    benchmark_pack_path = getattr(args, "benchmark_pack_path", None)
    con = get_console()

    def _pack_progress(current: int, total: int, label: str) -> None:
        con.progress(f"Pack {current}/{total}: {label}")

    try:
        result = run_official_pack(
            out_dir=out_dir,
            repo_root=root,
            seed_base=seed_base,
            smoke=smoke,
            full_security=full_security,
            pipeline_mode=pipeline_mode,
            allow_network=allow_network,
            llm_backend=llm_backend,
            include_coordination_pack=include_coordination_pack,
            partner_id=partner_id,
            metrics_aggregator_id=metrics_aggregator_id,
            benchmark_pack_path=benchmark_pack_path,
            progress_callback=_pack_progress,
        )
        get_console().write_plain(f"Official pack written to {result}")
        return 0
    except Exception as e:
        con = get_console()
        con.error(f"run-official-pack failed: {e}")
        if con.verbosity >= Verbosity.VERBOSE:
            con.print_exception(e)
        return 1


def _run_cross_provider_pack(args: argparse.Namespace) -> int:
    """Run official pack per provider; emit per-provider dirs and summary_cross_provider.json/.md."""
    get_console().info("Running run-cross-provider-pack.")
    from labtrust_gym.benchmarks.official_pack import run_cross_provider_pack

    root = get_repo_root()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    providers = [p.strip() for p in getattr(args, "providers", "").split(",") if p.strip()]
    if not providers:
        get_console().error("run-cross-provider-pack: --providers must be non-empty")
        return 1
    seed_base = getattr(args, "seed_base", 100)
    smoke = not getattr(args, "no_smoke", False)
    try:
        result = run_cross_provider_pack(
            out_dir=out_dir,
            repo_root=root,
            providers=providers,
            seed_base=seed_base,
            smoke=smoke,
        )
        get_console().write_plain(f"Cross-provider pack written to {result}")
        return 0
    except Exception as e:
        con = get_console()
        con.error(f"run-cross-provider-pack failed: {e}")
        if con.verbosity >= Verbosity.VERBOSE:
            con.print_exception(e)
        return 1


def _run_bench_smoke(args: argparse.Namespace) -> int:
    """Run 1 episode per task (throughput_sla, stat_insertion, qc_cascade); exit 0 if all succeed."""
    get_console().info("Running bench-smoke.")
    from labtrust_gym.benchmarks.runner import run_benchmark

    root = get_repo_root()
    seed = getattr(args, "seed", 42)
    tasks = ["throughput_sla", "stat_insertion", "qc_cascade"]
    for task in tasks:
        run_benchmark(
            task_name=task,
            num_episodes=1,
            base_seed=seed,
            out_path=root / f"bench_smoke_{task}.json",
            repo_root=root,
            metrics_aggregator_id=getattr(args, "metrics_aggregator_id", None),
        )
        get_console().write_plain(f"bench-smoke {task} OK (1 episode, seed={seed})")
    get_console().write_plain("bench-smoke all tasks OK.")
    return 0


def _run_record_llm_fixtures(args: argparse.Namespace) -> int:
    """Run a short benchmark with a live LLM backend and record fixtures. Manual use only; not for CI."""
    get_console().info("Running record-llm-fixtures.")
    repo_root = getattr(args, "repo_root", None) or get_repo_root()
    repo_root = Path(repo_root)
    llm_backend = getattr(args, "llm_backend", "openai_hosted") or "openai_hosted"
    if llm_backend in ("openai_hosted", "openai_live", "openai_responses") and not os.environ.get("OPENAI_API_KEY"):
        get_console().error(
            "record-llm-fixtures with --llm-backend openai_hosted/openai_live/openai_responses requires OPENAI_API_KEY."
        )
        return 1
    if llm_backend == "anthropic_live" and not os.environ.get("ANTHROPIC_API_KEY"):
        get_console().error("record-llm-fixtures with --llm-backend anthropic_live requires ANTHROPIC_API_KEY.")
        return 1
    from labtrust_gym.benchmarks.runner import run_benchmark

    task = getattr(args, "task", "insider_key_misuse")
    episodes = getattr(args, "episodes", 1)
    seed = getattr(args, "seed", 42)
    out_path = Path(getattr(args, "out", "runs/record_fixtures/results.json"))
    fixtures_dir = repo_root / "tests" / "fixtures" / "llm_responses"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_benchmark(
        task_name=task,
        num_episodes=episodes,
        base_seed=seed,
        out_path=out_path,
        repo_root=repo_root,
        llm_backend=llm_backend,
        llm_model=getattr(args, "llm_model", None),
        pipeline_mode="llm_live",
        allow_network=True,
        record_fixtures_path=fixtures_dir,
    )
    n = 0
    if out_path.exists():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            meta = data.get("metadata") or {}
            n = meta.get("recorded_fixtures", 0)
        except (json.JSONDecodeError, OSError):
            pass
    get_console().write_plain(f"Recorded {n} fixture(s) to {fixtures_dir}")
    return 0


def _run_record_coordination_fixtures(args: argparse.Namespace) -> int:
    """Run coord_risk/coord_scale with live coord backend and record coordination fixtures."""
    get_console().info("Running record-coordination-fixtures.")
    repo_root = getattr(args, "repo_root", None) or get_repo_root()
    repo_root = Path(repo_root)
    llm_backend = getattr(args, "llm_backend", "openai_live") or "openai_live"
    if llm_backend in ("openai_live",) and not os.environ.get("OPENAI_API_KEY"):
        get_console().error("record-coordination-fixtures with --llm-backend openai_live requires OPENAI_API_KEY.")
        return 1
    if llm_backend == "anthropic_live" and not os.environ.get("ANTHROPIC_API_KEY"):
        get_console().error("record-coordination-fixtures with anthropic_live requires ANTHROPIC_API_KEY.")
        return 1
    from labtrust_gym.benchmarks.runner import run_benchmark

    task = getattr(args, "task", "coord_risk")
    coord_method = getattr(args, "coord_method", "llm_central_planner")
    episodes = getattr(args, "episodes", 1)
    seed = getattr(args, "seed", 42)
    out_path = Path(getattr(args, "out", "runs/record_coord_fixtures/results.json"))
    coord_fixtures_dir = repo_root / "tests" / "fixtures" / "llm_responses"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_benchmark(
        task_name=task,
        num_episodes=episodes,
        base_seed=seed,
        out_path=out_path,
        repo_root=repo_root,
        coord_method=coord_method,
        injection_id="none",
        llm_backend=llm_backend,
        llm_model=getattr(args, "llm_model", None),
        pipeline_mode="llm_live",
        allow_network=True,
        record_coord_fixtures_path=coord_fixtures_dir,
    )
    n = 0
    if out_path.exists():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            meta = data.get("metadata") or {}
            n = meta.get("recorded_coord_fixtures", 0)
        except (json.JSONDecodeError, OSError):
            pass
    get_console().write_plain(f"Recorded {n} coordination fixture(s) to {coord_fixtures_dir}")
    return 0


def _run_replay_from_fixtures(args: argparse.Namespace) -> int:
    """Replay benchmark from fixtures (llm_offline, deterministic, no network)."""
    get_console().info("Running replay-from-fixtures.")
    repo_root = getattr(args, "repo_root", None) or get_repo_root()
    repo_root = Path(repo_root)
    task = getattr(args, "task", None)
    if not task:
        get_console().error("replay-from-fixtures requires --task.")
        return 1
    episodes = getattr(args, "episodes", 1)
    seed = getattr(args, "seed", 42)
    coord_method = getattr(args, "coord_method", None)
    if task in ("coord_risk", "coord_scale") and not coord_method:
        get_console().error(f"replay-from-fixtures for {task} requires --coord-method (e.g. llm_central_planner).")
        return 1
    coord_fixtures_path = getattr(args, "coord_fixtures_path", None)
    if coord_fixtures_path is None and task in ("coord_risk", "coord_scale"):
        coord_fixtures_path = repo_root / "tests" / "fixtures" / "llm_responses"
    out_path = getattr(args, "out", None)
    if not out_path:
        out_path = repo_root / "runs" / "replay_from_fixtures" / f"{task}_results.json"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from labtrust_gym.benchmarks.runner import run_benchmark

    run_benchmark(
        task_name=task,
        num_episodes=episodes,
        base_seed=seed,
        out_path=out_path,
        repo_root=repo_root,
        coord_method=coord_method,
        injection_id="none" if task == "coord_risk" else None,
        llm_backend="deterministic",
        pipeline_mode="llm_offline",
        coord_fixtures_path=coord_fixtures_path,
    )
    get_console().write_plain(f"Replay written to {out_path}")
    return 0


def _run_llm_healthcheck(args: argparse.Namespace) -> int:
    """Run one minimal request to live LLM backend; print ok, model_id, latency, usage."""
    get_console().info("Running llm-healthcheck.")
    from labtrust_gym.pipeline import set_pipeline_config

    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()
    if not allow_network:
        get_console().error("llm-healthcheck requires network. Pass --allow-network or set LABTRUST_ALLOW_NETWORK=1.")
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
    elif backend_name == "anthropic_live":
        from labtrust_gym.baselines.llm.backends.anthropic_live import (
            AnthropicLiveBackend,
        )

        backend = AnthropicLiveBackend(model=model_override)
    elif backend_name == "ollama_live":
        from labtrust_gym.baselines.llm.backends.ollama_live import OllamaLiveBackend

        backend = OllamaLiveBackend(model=model_override)
    else:
        from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend

        backend = OpenAILiveBackend(model=model_override)
    result = backend.healthcheck()
    ok = result.get("ok", False)
    get_console().write_plain(f"ok: {ok}")
    get_console().info(f"model_id: {result.get('model_id', 'n/a')}")
    get_console().info(f"latency_ms: {result.get('latency_ms')}")
    usage = result.get("usage") or {}
    if usage:
        get_console().info(f"usage: {usage}")
    if result.get("error"):
        get_console().error(f"error: {result['error']}")
    return 0 if ok else 1


def _run_serve(args: argparse.Namespace) -> int:
    """Start online HTTP server with abuse controls (B004)."""
    get_console().info("Running serve.")
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
    get_console().info(f"Serving at http://{config.host}:{config.port} (auth_required={config.auth_required})")
    run_server(config)
    return 0


def _run_quick_eval(args: argparse.Namespace) -> int:
    """Run 1 episode each of throughput_sla, adversarial_disruption, multi_site_stat; write markdown summary and logs under labtrust_runs/."""
    import json
    from datetime import datetime

    from labtrust_gym.benchmarks.runner import run_benchmark

    get_console().info(
        "Running quick-eval (1 episode per task: throughput_sla, adversarial_disruption, multi_site_stat)."
    )
    root = get_repo_root()
    seed = getattr(args, "seed", 42)
    out_dir = Path(getattr(args, "out_dir", "labtrust_runs"))
    if not out_dir.is_absolute():
        out_dir = root / out_dir
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = out_dir / f"quick_eval_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    pipeline_mode = getattr(args, "pipeline_mode", "deterministic") or "deterministic"
    allow_network = getattr(args, "allow_network", False) or _allow_network_from_env()

    tasks = ["throughput_sla", "adversarial_disruption", "multi_site_stat"]
    rows: list[dict[str, Any]] = []
    con = get_console()
    for i, task in enumerate(tasks):
        con.progress(f"Quick-eval task {i + 1}/{len(tasks)}: {task}")
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
            metrics_aggregator_id=getattr(args, "metrics_aggregator_id", None),
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
        lines.append(f"| {r['task']} | {r['throughput']} | {r['violation_count']} | {r['blocked_count']} |")
    lines.extend(["", f"Logs: `{logs_dir}`", ""])
    summary_path = run_dir / "summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    get_console().write_plain(f"quick-eval written to {run_dir}")
    print(summary_path.read_text(), file=sys.stdout)
    return 0


def _run_train_ppo(args: argparse.Namespace) -> int:
    """Train PPO and save model + eval metrics."""
    get_console().info("Running train-ppo.")
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    root = get_repo_root()
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    net_arch = None
    if getattr(args, "net_arch", None):
        net_arch = [int(x.strip()) for x in args.net_arch.split(",") if x.strip()]
    train_config: dict[str, Any] = {}
    config_path = getattr(args, "train_config", None)
    if config_path:
        p = Path(config_path)
        if not p.is_absolute():
            p = root / p
        if not p.exists():
            get_console().error(f"train-config file not found: {p}")
            return 1
        try:
            with open(p, encoding="utf-8") as f:
                train_config = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            get_console().error(f"Failed to load train-config: {e}")
            return 1
    if getattr(args, "obs_history_len", None) is not None:
        train_config["obs_history_len"] = max(1, int(args.obs_history_len))
    if getattr(args, "learning_rate", None) is not None:
        train_config["learning_rate"] = float(args.learning_rate)
    if getattr(args, "n_steps", None) is not None:
        train_config["n_steps"] = int(args.n_steps)
    result = train_ppo(
        task_name=args.task,
        timesteps=args.timesteps,
        seed=args.seed,
        out_dir=out,
        net_arch=net_arch,
        train_config=train_config if train_config else None,
        checkpoint_every_steps=getattr(args, "checkpoint_every", None),
        keep_best_checkpoints=getattr(args, "keep_best", 0) or 0,
    )
    get_console().write_plain(f"Model saved to {result['model_path']}")
    get_console().write_plain(f"Eval metrics to {result['eval_metrics_path']}")
    return 0


def _run_eval_ppo(args: argparse.Namespace) -> int:
    """Evaluate trained PPO policy."""
    get_console().info("Running eval-ppo.")
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
    get_console().write_plain(f"Mean reward: {metrics.get('mean_reward', 0):.2f}")
    if out_path:
        get_console().write_plain(f"Metrics written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
