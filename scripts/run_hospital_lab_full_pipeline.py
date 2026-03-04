#!/usr/bin/env python3
"""
Hospital lab full pipeline: collect end-to-end results (baselines, coordination pack,
security suite, safety case, optional method sweep) into a single output tree.

Uses existing run_official_pack, run_coordination_security_pack, run_suite_and_emit,
and optional run_all_coordination_methods_smoke. Writes a summary manifest under
summary/ for quick comparison.

Usage:
  python scripts/run_hospital_lab_full_pipeline.py --out runs/hospital_lab_full --matrix-preset hospital_lab
  python scripts/run_hospital_lab_full_pipeline.py --out runs/full --matrix-preset hospital_lab_full --security both --include-coordination-pack
  python scripts/run_hospital_lab_full_pipeline.py --out runs/cross --providers openai_live,anthropic_live --include-coordination-pack --allow-network
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_CONFIG_PATH = _SCRIPT_DIR / "hospital_lab_full_pipeline_config.yaml"


def _load_dotenv() -> None:
    """Load .env from repo root so OPENAI_API_KEY / ANTHROPIC_API_KEY are available in this process and child workers."""
    _env_file = _REPO_ROOT / ".env"
    if not _env_file.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_env_file)
    except ImportError:
        for line in _env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v


def _repo_root() -> Path:
    try:
        from labtrust_gym.config import get_repo_root

        return Path(get_repo_root())
    except ImportError:
        return _REPO_ROOT


def _load_config() -> dict[str, Any]:
    """Load scope config; return empty dict if missing."""
    if not _CONFIG_PATH.is_file():
        return {}
    from labtrust_gym.policy.loader import load_yaml

    data = load_yaml(_CONFIG_PATH)
    return data if isinstance(data, dict) else {}


def _run_official_pack(
    out_dir: Path,
    repo_root: Path,
    seed_base: int,
    smoke: bool,
    full_security: bool,
    include_coordination_pack: bool,
    matrix_preset: str | None,
    allow_network: bool = False,
    llm_backend: str | None = None,
    skip_system_level: bool = False,
) -> Path:
    from labtrust_gym.benchmarks.official_pack import run_official_pack

    return run_official_pack(
        out_dir=out_dir,
        repo_root=repo_root,
        seed_base=seed_base,
        smoke=smoke,
        full_security=full_security,
        pipeline_mode="llm_live" if (llm_backend and allow_network) else "deterministic",
        allow_network=allow_network,
        llm_backend=llm_backend,
        include_coordination_pack=include_coordination_pack,
        matrix_preset_override=matrix_preset if include_coordination_pack else None,
        skip_system_level=skip_system_level,
    )


def _run_cross_provider_pack(
    out_dir: Path,
    repo_root: Path,
    providers: list[str],
    seed_base: int,
    smoke: bool,
    full_security: bool,
    skip_system_level: bool = False,
) -> Path:
    from labtrust_gym.benchmarks.official_pack import run_cross_provider_pack

    return run_cross_provider_pack(
        out_dir=out_dir,
        repo_root=repo_root,
        providers=providers,
        seed_base=seed_base,
        smoke=smoke,
        full_security=full_security,
        skip_system_level=skip_system_level,
    )


def _run_coordination_pack_standalone(
    out_dir: Path,
    repo_root: Path,
    seed_base: int,
    matrix_preset: str,
    llm_backend: str | None = None,
    allow_network: bool = False,
) -> None:
    from labtrust_gym.studies.coordination_security_pack import run_coordination_security_pack
    from labtrust_gym.studies.lab_report_builder import build_lab_coordination_report

    run_coordination_security_pack(
        out_dir=out_dir,
        repo_root=repo_root,
        seed_base=seed_base,
        matrix_preset=matrix_preset,
        llm_backend=llm_backend,
        allow_network=allow_network,
    )
    build_lab_coordination_report(
        pack_dir=out_dir,
        out_dir=out_dir,
        policy_root=repo_root,
        matrix_preset_name=matrix_preset,
    )


def _run_security_suite_extra(
    out_dir: Path,
    repo_root: Path,
    seed_base: int,
    smoke_only: bool,
    llm_attacker: bool = False,
    allow_network: bool = False,
    llm_backend: str | None = None,
) -> None:
    from labtrust_gym.benchmarks.securitization import emit_securitization_packet
    from labtrust_gym.benchmarks.security_runner import run_suite_and_emit

    run_suite_and_emit(
        policy_root=repo_root,
        out_dir=out_dir,
        repo_root=repo_root,
        smoke_only=smoke_only,
        seed=seed_base,
        metadata={"seed_base": seed_base, "smoke_only": smoke_only},
        llm_attacker=llm_attacker,
        allow_network=allow_network,
        llm_backend=llm_backend,
    )
    emit_securitization_packet(repo_root, out_dir)


def _run_method_sweep(out_dir: Path, repo_root: Path, seed: int) -> int:
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "run_all_coordination_methods_smoke.py"),
        "--preset",
        "full",
        "--out",
        str(out_dir),
        "--seed",
        str(seed),
    ]
    r = subprocess.run(cmd, cwd=str(repo_root), timeout=3600)
    return r.returncode


def _write_summary_manifest(
    out_root: Path,
    manifest: dict[str, Any],
) -> None:
    summary_dir = out_root / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = summary_dir / "full_pipeline_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    md_path = summary_dir / "full_pipeline_manifest.md"
    lines = [
        "# Hospital lab full pipeline – summary",
        "",
        f"Generated: {manifest.get('timestamp', '')}",
        f"Seed base: {manifest.get('seed_base')}",
        f"Matrix preset: {manifest.get('matrix_preset', 'n/a')}",
        f"Security: {manifest.get('security_mode', 'n/a')}",
        f"Include coordination pack: {manifest.get('include_coordination_pack', False)}",
        "",
        "## Artifacts",
        "",
        "| Path | Description |",
        "|------|-------------|",
    ]
    for entry in manifest.get("artifacts", []):
        path = entry.get("path", "")
        desc = entry.get("description", "")
        lines.append(f"| {path} | {desc} |")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run hospital lab full pipeline: baselines, coordination pack, security, safety, optional method sweep.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output root directory (e.g. runs/hospital_lab_full_pipeline).",
    )
    parser.add_argument(
        "--matrix-preset",
        default="hospital_lab",
        choices=["hospital_lab", "hospital_lab_full", "full_matrix"],
        help="Coordination pack matrix preset (default: hospital_lab).",
    )
    parser.add_argument(
        "--security",
        default="smoke",
        choices=["smoke", "full", "both"],
        help="Security suite: smoke (default), full, or both (smoke in pack + full in security_full/).",
    )
    parser.add_argument(
        "--include-coordination-pack",
        action="store_true",
        help="Run coordination security pack and build lab report.",
    )
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated LLM providers (e.g. openai_live,anthropic_live). If set, run cross-provider pack instead of single pack.",
    )
    parser.add_argument(
        "--seed-base",
        type=int,
        default=42,
        help="Base seed (default: 42).",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network (for live LLM or cross-provider).",
    )
    parser.add_argument(
        "--no-smoke",
        action="store_true",
        help="Disable smoke; run full pack (more episodes).",
    )
    parser.add_argument(
        "--llm-attacker",
        action="store_true",
        help="Run security suite with LLM attacker into security_llm_attacker/ (requires --allow-network and API key).",
    )
    parser.add_argument(
        "--llm-backend",
        default=None,
        help="LLM backend for llm_attacker (e.g. openai_live).",
    )
    parser.add_argument(
        "--method-sweep",
        action="store_true",
        help="Run run_all_coordination_methods_smoke (preset full) into method_sweep/.",
    )
    parser.add_argument(
        "--models",
        default="",
        help="Per-model sweep: comma-separated 'backend:model_id' (e.g. openai_live:gpt-4o-mini,openai_live:gpt-4o). Requires --allow-network.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to scope config YAML (default: scripts/hospital_lab_full_pipeline_config.yaml).",
    )
    args = parser.parse_args()

    _load_dotenv()

    repo_root = _repo_root()
    out_root = Path(args.out).resolve()
    if not out_root.is_absolute():
        out_root = repo_root / out_root
    out_root.mkdir(parents=True, exist_ok=True)

    _config = _load_config() if not args.config else {}
    if args.config and Path(args.config).is_file():
        from labtrust_gym.policy.loader import load_yaml

        _ = load_yaml(Path(args.config)) or {}  # validate config loads

    smoke = not args.no_smoke
    full_security = args.security in ("full", "both")
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    matrix_preset = args.matrix_preset
    seed_base = args.seed_base

    model_pairs: list[tuple[str, str]] = []
    if args.models:
        for part in args.models.split(","):
            part = part.strip()
            if ":" in part:
                backend, model_id = part.split(":", 1)
                model_pairs.append((backend.strip(), model_id.strip()))
            elif part:
                model_pairs.append(("openai_live", part))
        if model_pairs and not args.allow_network:
            print("Warning: --models requires --allow-network; skipping per-model sweep.", file=sys.stderr)
            model_pairs = []

    artifacts: list[dict[str, str]] = []
    manifest: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "seed_base": seed_base,
        "matrix_preset": matrix_preset,
        "security_mode": args.security,
        "include_coordination_pack": args.include_coordination_pack,
        "providers": providers,
        "models_sweep": [f"{b}:{m}" for b, m in model_pairs],
        "artifacts": artifacts,
    }

    def _set_model_env(backend: str, model_id: str) -> None:
        if "openai" in backend.lower():
            os.environ["LABTRUST_OPENAI_MODEL"] = model_id
        elif "anthropic" in backend.lower():
            os.environ["LABTRUST_ANTHROPIC_MODEL"] = model_id
        elif "ollama" in backend.lower():
            os.environ["LABTRUST_OLLAMA_MODEL"] = model_id

    skip_system_level = sys.platform == "win32"
    try:
        if model_pairs:
            models_dir = out_root / "models"
            models_dir.mkdir(parents=True, exist_ok=True)
            for backend, model_id in model_pairs:
                subdir = models_dir / backend.replace("/", "_") / model_id.replace("/", "_")
                subdir.mkdir(parents=True, exist_ok=True)
                _set_model_env(backend, model_id)
                print(f"Running official pack for {backend} / {model_id}...", file=sys.stderr)
                _run_official_pack(
                    out_dir=subdir,
                    repo_root=repo_root,
                    seed_base=seed_base,
                    smoke=smoke,
                    full_security=args.security == "full",
                    include_coordination_pack=False,
                    matrix_preset=None,
                    allow_network=True,
                    llm_backend=backend,
                    skip_system_level=skip_system_level,
                )
                artifacts.append(
                    {"path": f"models/{backend}/{model_id}/", "description": f"Pack for {backend} model {model_id}"}
                )
            if args.include_coordination_pack:
                coord_dir = out_root / "coordination_pack"
                coord_dir.mkdir(parents=True, exist_ok=True)
                try:
                    print(f"Running coordination pack (matrix_preset={matrix_preset})...", file=sys.stderr)
                    _run_coordination_pack_standalone(
                        out_dir=coord_dir,
                        repo_root=repo_root,
                        seed_base=seed_base,
                        matrix_preset=matrix_preset,
                        llm_backend=providers[0] if providers else None,
                        allow_network=bool(providers),
                    )
                    artifacts.append(
                        {"path": "coordination_pack/", "description": "Coordination security pack and lab report"}
                    )
                except Exception as e:
                    print(f"Coordination pack failed (continuing): {e}", file=sys.stderr)
                    artifacts.append(
                        {
                            "path": "coordination_pack/",
                            "description": "Coordination security pack (failed)",
                            "error": str(e)[:500],
                        }
                    )
        elif providers:
            print("Running cross-provider pack...", file=sys.stderr)
            _run_cross_provider_pack(
                out_dir=out_root,
                repo_root=repo_root,
                providers=providers,
                seed_base=seed_base,
                smoke=smoke,
                full_security=full_security,
                skip_system_level=skip_system_level,
            )
            for p in providers:
                artifacts.append({"path": f"{p}/", "description": f"Official pack output for provider {p}"})
            if args.include_coordination_pack:
                coord_dir = out_root / "coordination_pack"
                coord_dir.mkdir(parents=True, exist_ok=True)
                try:
                    print(f"Running coordination pack (matrix_preset={matrix_preset})...", file=sys.stderr)
                    _run_coordination_pack_standalone(
                        out_dir=coord_dir,
                        repo_root=repo_root,
                        seed_base=seed_base,
                        matrix_preset=matrix_preset,
                        llm_backend=providers[0],
                        allow_network=True,
                    )
                    artifacts.append(
                        {"path": "coordination_pack/", "description": "Coordination security pack and lab report"}
                    )
                except Exception as e:
                    print(f"Coordination pack failed (continuing): {e}", file=sys.stderr)
                    artifacts.append(
                        {
                            "path": "coordination_pack/",
                            "description": "Coordination security pack (failed)",
                            "error": str(e)[:500],
                        }
                    )
        else:
            print("Running official pack...", file=sys.stderr)
            pack_full_security = args.security == "full"
            _run_official_pack(
                out_dir=out_root,
                repo_root=repo_root,
                seed_base=seed_base,
                smoke=smoke,
                full_security=pack_full_security,
                include_coordination_pack=args.include_coordination_pack,
                matrix_preset=matrix_preset if args.include_coordination_pack else None,
                allow_network=args.allow_network,
                llm_backend=None,
                skip_system_level=skip_system_level,
            )
            artifacts.append({"path": "baselines/", "description": "Baseline results"})
            artifacts.append({"path": "SECURITY/", "description": "Security attack results and coverage"})
            artifacts.append({"path": "SAFETY_CASE/", "description": "Safety case"})
            artifacts.append({"path": "TRANSPARENCY_LOG/", "description": "Transparency log"})
            if args.include_coordination_pack:
                artifacts.append(
                    {"path": "coordination_pack/", "description": "Coordination security pack and lab report"}
                )

        if args.security == "full" or args.security == "both":
            sec_full_dir = out_root / "security_full"
            sec_full_dir.mkdir(parents=True, exist_ok=True)
            try:
                print("Running security suite (full)...", file=sys.stderr)
                _run_security_suite_extra(
                    out_dir=sec_full_dir,
                    repo_root=repo_root,
                    seed_base=seed_base,
                    smoke_only=False,
                )
                artifacts.append({"path": "security_full/", "description": "Security suite full run"})
            except Exception as e:
                print(f"Security full failed (continuing): {e}", file=sys.stderr)
                artifacts.append(
                    {"path": "security_full/", "description": "Security suite full (failed)", "error": str(e)[:500]}
                )

        if args.llm_attacker:
            sec_llm_dir = out_root / "security_llm_attacker"
            sec_llm_dir.mkdir(parents=True, exist_ok=True)
            try:
                print("Running security suite (LLM attacker)...", file=sys.stderr)
                _run_security_suite_extra(
                    out_dir=sec_llm_dir,
                    repo_root=repo_root,
                    seed_base=seed_base,
                    smoke_only=True,
                    llm_attacker=True,
                    allow_network=args.allow_network,
                    llm_backend=args.llm_backend or "openai_live",
                )
                artifacts.append({"path": "security_llm_attacker/", "description": "Security suite with LLM attacker"})
            except Exception as e:
                print(f"Security LLM attacker failed (continuing): {e}", file=sys.stderr)
                artifacts.append(
                    {
                        "path": "security_llm_attacker/",
                        "description": "Security suite LLM attacker (failed)",
                        "error": str(e)[:500],
                    }
                )

        if args.method_sweep:
            sweep_dir = out_root / "method_sweep"
            sweep_dir.mkdir(parents=True, exist_ok=True)
            try:
                print("Running method sweep (all coordination methods)...", file=sys.stderr)
                rc = _run_method_sweep(out_dir=sweep_dir, repo_root=repo_root, seed=seed_base)
                if rc != 0:
                    print(f"Warning: method sweep exited with {rc}", file=sys.stderr)
                artifacts.append({"path": "method_sweep/", "description": "All coordination methods summary"})
            except Exception as e:
                print(f"Method sweep failed (continuing): {e}", file=sys.stderr)
                artifacts.append(
                    {"path": "method_sweep/", "description": "Method sweep (failed)", "error": str(e)[:500]}
                )

        manifest["artifacts"] = artifacts
        _write_summary_manifest(out_root, manifest)
        print(f"Summary manifest: {out_root / 'summary' / 'full_pipeline_manifest.json'}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Pipeline failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        manifest["pipeline_error"] = str(e)[:500]
        manifest["partial"] = True
        manifest["artifacts"] = artifacts
        try:
            _write_summary_manifest(out_root, manifest)
            print(f"Partial summary written: {out_root / 'summary' / 'full_pipeline_manifest.json'}", file=sys.stderr)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
