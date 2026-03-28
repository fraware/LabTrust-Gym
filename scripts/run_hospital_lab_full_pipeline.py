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
  python scripts/run_hospital_lab_full_pipeline.py --out runs/pi_top6 --allow-network --benchmark-models-from-config
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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


def _sanitize_tls_env() -> None:
    """
    Guard against broken TLS env settings that can crash httpx/OpenAI client init.
    If SSL_CERT_FILE points to a missing file, unset it and rely on defaults.
    """
    cert_file = (os.environ.get("SSL_CERT_FILE") or "").strip()
    if cert_file and not Path(cert_file).is_file():
        print(
            f"Warning: SSL_CERT_FILE points to missing file ({cert_file}); unsetting for this run.",
            file=sys.stderr,
        )
        os.environ.pop("SSL_CERT_FILE", None)


def _repo_root() -> Path:
    try:
        from labtrust_gym.config import get_repo_root

        return Path(get_repo_root())
    except ImportError:
        return _REPO_ROOT


def _load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load scope config from default path or override; return empty dict if missing."""
    path = config_path if config_path is not None else _CONFIG_PATH
    if not path.is_file():
        return {}
    from labtrust_gym.policy.loader import load_yaml

    data = load_yaml(path)
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
    episodes_per_task: int | None = None,
    progress_prefix: str | None = None,
) -> Path:
    from labtrust_gym.benchmarks.official_pack import run_official_pack

    t0 = time.perf_counter()

    def _progress(cur: int, total: int, stage: str) -> None:
        if not progress_prefix:
            return
        elapsed_s = int(time.perf_counter() - t0)
        print(f"[{progress_prefix}] {cur}/{total} {stage} (elapsed={elapsed_s}s)", file=sys.stderr)

    return run_official_pack(
        out_dir=out_dir,
        repo_root=repo_root,
        seed_base=seed_base,
        smoke=smoke,
        full_security=full_security,
        episodes_per_task=episodes_per_task,
        pipeline_mode="llm_live" if (llm_backend and allow_network) else "deterministic",
        allow_network=allow_network,
        llm_backend=llm_backend,
        include_coordination_pack=include_coordination_pack,
        matrix_preset_override=matrix_preset if include_coordination_pack else None,
        skip_system_level=skip_system_level,
        progress_callback=_progress if progress_prefix else None,
    )


def _preflight_live_model(backend: str, model_id: str | None) -> tuple[bool, str]:
    """
    One cheap live request before long packs.
    Returns (ok, message). On failure, callers can skip/abort expensive runs.
    """
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(pipeline_mode="llm_live", allow_network=True, llm_backend_id=backend)
    try:
        if backend == "prime_intellect_live":
            from labtrust_gym.baselines.llm.backends.prime_intellect_live import PrimeIntellectLiveBackend
            from labtrust_gym.baselines.llm.credentials import resolve_credentials

            creds = resolve_credentials(backend, _REPO_ROOT)
            be = PrimeIntellectLiveBackend(**creds, model=model_id)
        elif backend == "openai_live":
            from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend
            from labtrust_gym.baselines.llm.credentials import resolve_credentials

            creds = resolve_credentials(backend, _REPO_ROOT)
            be = OpenAILiveBackend(**creds, model=model_id)
        elif backend == "anthropic_live":
            from labtrust_gym.baselines.llm.backends.anthropic_live import AnthropicLiveBackend
            from labtrust_gym.baselines.llm.credentials import resolve_credentials

            creds = resolve_credentials(backend, _REPO_ROOT)
            be = AnthropicLiveBackend(**creds, model=model_id)
        elif backend == "ollama_live":
            from labtrust_gym.baselines.llm.backends.ollama_live import OllamaLiveBackend

            be = OllamaLiveBackend(model=model_id)
        else:
            return True, "preflight skipped (unsupported backend)"
        out = be.healthcheck()
        if bool(out.get("ok")):
            return True, f"ok (model={out.get('model_id')})"
        err = str(out.get("error") or "healthcheck failed")[:240]
        return False, err
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:240]


def _discover_prime_models_live(limit: int = 200) -> tuple[set[str], str | None]:
    """
    Return available model IDs from Prime Inference models endpoint.
    Best-effort only: returns ({}, error_message) on failure.
    """
    try:
        from openai import OpenAI
    except Exception as e:  # noqa: BLE001
        return set(), f"openai SDK unavailable: {e}"
    key = (os.environ.get("PRIME_INTELLECT_API_KEY") or os.environ.get("PRIME_API_KEY") or "").strip()
    if not key:
        return set(), "PRIME_INTELLECT_API_KEY/PRIME_API_KEY missing"
    base = (os.environ.get("LABTRUST_PRIME_INTELLECT_BASE_URL") or "https://api.pinference.ai/api/v1").strip()
    headers: dict[str, str] = {}
    team = (os.environ.get("LABTRUST_PRIME_TEAM_ID") or "").strip()
    if team:
        headers["X-Prime-Team-ID"] = team
    try:
        kwargs: dict[str, Any] = {"api_key": key, "base_url": base}
        if headers:
            kwargs["default_headers"] = headers
        client = OpenAI(**kwargs)
        data = client.models.list()
        out: set[str] = set()
        for row in getattr(data, "data", [])[:limit]:
            mid = str(getattr(row, "id", "") or "").strip()
            if mid:
                out.add(mid)
        return out, None
    except Exception as e:  # noqa: BLE001
        return set(), str(e)[:240]


def _looks_like_model_pack_failed(subdir: Path) -> tuple[bool, str]:
    """
    Detect pathological runs that consume long time with no useful LLM output.
    """
    results_dir = subdir / "baselines" / "results"
    files = sorted(results_dir.glob("*.json"))
    if not files:
        return True, "no baseline result JSON produced"
    n = 0
    bad = 0
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = data.get("metadata") or {}
        er = meta.get("llm_error_rate")
        tt = meta.get("total_tokens")
        if isinstance(er, (int, float)):
            n += 1
            if float(er) >= 0.99 and (tt is None or int(tt) == 0):
                bad += 1
    if n > 0 and bad == n:
        return True, f"all tasks show llm_error_rate>=0.99 with zero tokens ({bad}/{n})"
    return False, ""


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
        "--benchmark-models-from-config",
        action="store_true",
        help="Append per-model sweep entries from prime_intellect_benchmark_models in the scope config (requires --allow-network).",
    )
    parser.add_argument(
        "--episodes-per-task",
        type=int,
        default=None,
        help="Override episodes per task passed into official pack (default: pack default; no-smoke uses many episodes).",
    )
    parser.add_argument(
        "--max-models",
        type=int,
        default=0,
        help="Run at most N models from sweep list (0 = all). Useful to cap long runs.",
    )
    parser.add_argument(
        "--skip-preflight-healthcheck",
        action="store_true",
        help="Skip one-request model preflight before expensive full pack runs.",
    )
    parser.add_argument(
        "--abort-on-preflight-failure",
        action="store_true",
        help="Abort entire pipeline if a model preflight fails (default: skip failed model and continue).",
    )
    parser.add_argument(
        "--abort-on-model-failure",
        action="store_true",
        help="Abort pipeline if a model pack looks pathological (e.g. all tasks at llm_error_rate~=1 with zero tokens).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to scope config YAML (default: scripts/hospital_lab_full_pipeline_config.yaml).",
    )
    args = parser.parse_args()

    _load_dotenv()
    _sanitize_tls_env()

    repo_root = _repo_root()
    out_root = Path(args.out).resolve()
    if not out_root.is_absolute():
        out_root = repo_root / out_root
    out_root.mkdir(parents=True, exist_ok=True)

    _config_path = Path(args.config) if args.config else _CONFIG_PATH
    _config = _load_config(_config_path)

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

    if args.benchmark_models_from_config and isinstance(_config.get("prime_intellect_benchmark_models"), list):
        if not args.allow_network:
            print(
                "Warning: --benchmark-models-from-config requires --allow-network; ignoring config model list.",
                file=sys.stderr,
            )
        else:
            for entry in _config["prime_intellect_benchmark_models"]:
                if isinstance(entry, dict):
                    b = str(entry.get("backend", "")).strip()
                    m = str(entry.get("model_id", "")).strip()
                    if b and m:
                        model_pairs.append((b, m))
                elif isinstance(entry, str) and ":" in entry:
                    b, sep, m = entry.partition(":")
                    if sep:
                        model_pairs.append((b.strip(), m.strip()))
        # Auto-filter Prime models by live /models so invalid IDs are skipped upfront.
        if args.allow_network:
            avail, err = _discover_prime_models_live()
            if avail:
                before = len(model_pairs)
                filtered: list[tuple[str, str]] = []
                for b, m in model_pairs:
                    if b == "prime_intellect_live":
                        if m in avail:
                            filtered.append((b, m))
                        else:
                            print(
                                f"Skipping unavailable Prime model from config: {m}",
                                file=sys.stderr,
                            )
                    else:
                        filtered.append((b, m))
                model_pairs = filtered
                kept = len(model_pairs)
                print(
                    f"Prime model discovery filter: kept {kept}/{before} configured entries.",
                    file=sys.stderr,
                )
            elif err:
                print(f"Warning: Prime model discovery failed, keeping configured list ({err})", file=sys.stderr)

    # Deduplicate while preserving order.
    dedup_pairs: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for b, m in model_pairs:
        key = (b, m)
        if key in seen_pairs:
            continue
        dedup_pairs.append(key)
        seen_pairs.add(key)
    model_pairs = dedup_pairs

    coord_pack_backend: str | None = None
    if args.include_coordination_pack and model_pairs:
        from labtrust_gym.studies.coordination_security_pack import (
            assert_unique_llm_backend_for_coordination_model_sweep,
        )

        coord_pack_backend = assert_unique_llm_backend_for_coordination_model_sweep(model_pairs)

    artifacts: list[dict[str, str]] = []
    manifest: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "seed_base": seed_base,
        "matrix_preset": matrix_preset,
        "security_mode": args.security,
        "include_coordination_pack": args.include_coordination_pack,
        "providers": providers,
        "models_sweep": [f"{b}:{m}" for b, m in model_pairs],
        "coordination_pack_llm_backend": coord_pack_backend,
        "artifacts": artifacts,
    }

    def _set_model_env(backend: str, model_id: str) -> None:
        if "openai" in backend.lower():
            os.environ["LABTRUST_OPENAI_MODEL"] = model_id
        elif "anthropic" in backend.lower():
            os.environ["LABTRUST_ANTHROPIC_MODEL"] = model_id
        elif "ollama" in backend.lower():
            os.environ["LABTRUST_OLLAMA_MODEL"] = model_id
        elif "prime_intellect" in backend.lower():
            os.environ["LABTRUST_PRIME_INTELLECT_MODEL"] = model_id

    skip_system_level = sys.platform == "win32"
    try:
        if model_pairs:
            models_dir = out_root / "models"
            models_dir.mkdir(parents=True, exist_ok=True)
            started_model_runs = 0
            for backend, model_id in model_pairs:
                if args.max_models and args.max_models > 0 and started_model_runs >= args.max_models:
                    print(f"Reached --max-models={args.max_models}; stopping model sweep.", file=sys.stderr)
                    break
                subdir = models_dir / backend.replace("/", "_") / model_id.replace("/", "_")
                subdir.mkdir(parents=True, exist_ok=True)
                _set_model_env(backend, model_id)
                if not args.skip_preflight_healthcheck and backend in (
                    "prime_intellect_live",
                    "openai_live",
                    "anthropic_live",
                    "ollama_live",
                ):
                    ok, msg = _preflight_live_model(backend, model_id)
                    if ok:
                        print(f"Preflight OK for {backend} / {model_id}: {msg}", file=sys.stderr)
                    else:
                        print(f"Preflight FAILED for {backend} / {model_id}: {msg}", file=sys.stderr)
                        if args.abort_on_preflight_failure:
                            raise RuntimeError(f"Preflight failed for {backend}:{model_id}: {msg}")
                        artifacts.append(
                            {
                                "path": f"models/{backend}/{model_id}/",
                                "description": f"Skipped after preflight failure for {backend} model {model_id}",
                                "error": msg,
                            }
                        )
                        continue
                print(f"Running official pack for {backend} / {model_id}...", file=sys.stderr)
                started_model_runs += 1
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
                    episodes_per_task=args.episodes_per_task,
                    progress_prefix=f"{backend}:{model_id}",
                )
                failed_model, reason = _looks_like_model_pack_failed(subdir)
                artifacts.append(
                    {"path": f"models/{backend}/{model_id}/", "description": f"Pack for {backend} model {model_id}"}
                )
                if failed_model:
                    print(f"Model run flagged as pathological for {backend}/{model_id}: {reason}", file=sys.stderr)
                    if args.abort_on_model_failure:
                        raise RuntimeError(f"Aborting on model failure: {backend}:{model_id}: {reason}")
            if args.include_coordination_pack:
                coord_dir = out_root / "coordination_pack"
                coord_dir.mkdir(parents=True, exist_ok=True)
                try:
                    assert coord_pack_backend is not None  # set when include_coordination_pack and model_pairs
                    print(
                        f"Running coordination pack (matrix_preset={matrix_preset}, "
                        f"llm_backend={coord_pack_backend!r}, allow_network=True)...",
                        file=sys.stderr,
                    )
                    _run_coordination_pack_standalone(
                        out_dir=coord_dir,
                        repo_root=repo_root,
                        seed_base=seed_base,
                        matrix_preset=matrix_preset,
                        llm_backend=coord_pack_backend,
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
