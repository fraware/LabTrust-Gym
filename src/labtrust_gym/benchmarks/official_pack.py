"""
Official Benchmark Pack runner (v0.1 and v0.2).

Loads the pack policy (v0.1 or v0.2 when pipeline mode is llm_live). Runs
baselines, security suite, safety case, and transparency log into a single
output folder. For llm_live mode also writes transparency and live evaluation
metadata. Results follow the v0.2 schema. Used by package-release and the CLI.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from labtrust_gym.config import policy_path
from labtrust_gym.policy.loader import load_yaml

logger = logging.getLogger(__name__)

PACK_POLICY_PATH = "policy/official/benchmark_pack.v0.1.yaml"
PACK_POLICY_PATH_V02 = "policy/official/benchmark_pack.v0.2.yaml"
LIVE_EVALUATION_METADATA_FILENAME = "live_evaluation_metadata.json"

# Optional custom pack loaders: register_benchmark_pack_loader(loader_id, loader).
# Loader signature: (repo_root: Path, prefer_v02: bool, partner_id: str | None) -> tuple[dict, str, str].
_BENCHMARK_PACK_LOADERS: dict[str, Callable[..., tuple[dict[str, Any], str, str]]] = {}


def register_benchmark_pack_loader(
    loader_id: str,
    loader: Callable[[Path, bool, str | None], tuple[dict[str, Any], str, str]],
) -> None:
    """Register a custom benchmark pack loader. Overwrites if present."""
    _BENCHMARK_PACK_LOADERS[loader_id] = loader


def get_benchmark_pack_loader(
    loader_id: str,
) -> Callable[[Path, bool, str | None], tuple[dict[str, Any], str, str]] | None:
    """Return the registered loader for loader_id, or None."""
    return _BENCHMARK_PACK_LOADERS.get(loader_id)


DEFAULT_ROLE_MIX = {
    "ROLE_RUNNER": 0.4,
    "ROLE_ANALYTICS": 0.3,
    "ROLE_RECEPTION": 0.2,
    "ROLE_QC": 0.05,
    "ROLE_SUPERVISOR": 0.05,
}


def load_benchmark_pack(
    repo_root: Path,
    prefer_v02: bool = False,
    partner_id: str | None = None,
    loader_id: str | None = None,
    pack_path: Path | None = None,
) -> tuple[dict[str, Any], str, str]:
    """
    Load benchmark pack YAML. When prefer_v02 is True, load v0.2 if present, else v0.1.
    When partner_id is set, try policy/partners/<id>/official/benchmark_pack.v0.1.yaml first.
    When loader_id is set and registered, use that loader instead of file-based load.
    When pack_path is set and exists, load from that path (profile path override).
    Returns (pack_dict, version_string, pack_policy_path).
    """
    if loader_id:
        loader = get_benchmark_pack_loader(loader_id)
        if loader is not None:
            return loader(repo_root, prefer_v02, partner_id)
    if pack_path is not None and pack_path.exists():
        data = load_yaml(pack_path)
        default_pack = {
            "version": "0.1",
            "tasks": {"core": [], "coordination": [], "experimental": []},
            "scale_configs": {},
            "baselines": {},
            "coordination_methods": [],
            "security_suite": {"smoke": {"enabled": True}, "full": {"enabled": False}},
            "required_reports": ["security", "safety_case", "transparency_log"],
        }
        pack = data if isinstance(data, dict) else default_pack
        version = pack.get("version", "0.1")
        try:
            path_str = pack_path.relative_to(repo_root).as_posix()
        except ValueError:
            path_str = str(pack_path)
        return pack, str(version), path_str
    default_pack = {
        "version": "0.1",
        "tasks": {"core": [], "coordination": [], "experimental": []},
        "scale_configs": {},
        "baselines": {},
        "coordination_methods": [],
        "security_suite": {"smoke": {"enabled": True}, "full": {"enabled": False}},
        "required_reports": ["security", "safety_case", "transparency_log"],
    }
    if partner_id:
        overlay_v01 = policy_path(repo_root, "partners", partner_id, "official", "benchmark_pack.v0.1.yaml")
        if overlay_v01.exists():
            data = load_yaml(overlay_v01)
            pack = data if isinstance(data, dict) else default_pack
            version = pack.get("version", "0.1")
            return pack, str(version), overlay_v01.relative_to(repo_root).as_posix()
    path_v02 = policy_path(repo_root, "official", "benchmark_pack.v0.2.yaml")
    path_v01 = policy_path(repo_root, "official", "benchmark_pack.v0.1.yaml")
    if prefer_v02 and path_v02.exists():
        data = load_yaml(path_v02)
        pack = data if isinstance(data, dict) else default_pack
        version = pack.get("version", "0.2")
        return pack, str(version), PACK_POLICY_PATH_V02
    if path_v01.exists():
        data = load_yaml(path_v01)
        pack = data if isinstance(data, dict) else default_pack
        version = pack.get("version", "0.1")
        return pack, str(version), PACK_POLICY_PATH
    return default_pack, "0.1", PACK_POLICY_PATH


def _all_pack_tasks(pack: dict[str, Any]) -> list[str]:
    """Return ordered list of task names (core + coordination + experimental)."""
    out: list[str] = []
    for key in ("core", "coordination", "experimental"):
        out.extend(pack.get("tasks", {}).get(key) or [])
    return out


def _scale_config_to_coordination_scale_config(scale_id: str, scale_row: dict[str, Any]) -> Any:
    """Build CoordinationScaleConfig from pack scale_configs entry."""
    from labtrust_gym.benchmarks.coordination_scale import CoordinationScaleConfig

    num_agents = int(scale_row.get("num_agents_total", 4))
    num_devices = int(scale_row.get("num_devices", 2))
    num_sites = int(scale_row.get("num_sites", 1))
    arrival_rate = float(scale_row.get("arrival_rate", 1.0))
    horizon_steps = int(scale_row.get("horizon_steps", 200))
    return CoordinationScaleConfig(
        num_agents_total=num_agents,
        role_mix=dict(DEFAULT_ROLE_MIX),
        num_devices_per_type={
            "CHEM_ANALYZER": num_devices,
            "CENTRIFUGE_BANK": max(1, num_devices // 2),
        },
        num_sites=num_sites,
        specimens_per_min=arrival_rate,
        horizon_steps=horizon_steps,
        timing_mode="explicit",
        coord_auction_protocol=scale_row.get("coord_auction_protocol"),
    )


def run_official_pack(
    out_dir: Path,
    repo_root: Path,
    seed_base: int,
    smoke: bool = True,
    full_security: bool = False,
    episodes_per_task: int | None = None,
    pipeline_mode: str = "deterministic",
    allow_network: bool = False,
    llm_backend: str | None = None,
    include_coordination_pack: bool | None = None,
    matrix_preset_override: str | None = None,
    partner_id: str | None = None,
    metrics_aggregator_id: str | None = None,
    benchmark_pack_path: Path | None = None,
    security_suite_timeout_s: int = 300,
    skip_system_level: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Path:
    """
    Run the official benchmark pack: baselines, SECURITY/, SAFETY_CASE/, TRANSPARENCY_LOG/.
    Returns out_dir. When smoke=True, uses fewer episodes and security smoke-only.
    When pipeline_mode is llm_live, pass llm_backend (e.g. openai_responses, anthropic_live) to use that backend for baselines.
    When include_coordination_pack is True (or pack policy coordination_pack.enabled), runs
    coordination security pack into coordination_pack/ and builds lab report there.
    matrix_preset_override: when set (e.g. hospital_lab_full), use this preset for the coordination pack instead of pack policy.
    """
    out_dir = Path(out_dir).resolve()
    repo_root = Path(repo_root).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    prefer_v02 = pipeline_mode == "llm_live"
    pack, pack_version, pack_policy_path = load_benchmark_pack(
        repo_root, prefer_v02=prefer_v02, partner_id=partner_id, pack_path=benchmark_pack_path
    )
    tasks_raw = _all_pack_tasks(pack)
    import labtrust_gym.benchmarks.tasks as _tasks_mod

    _registry = getattr(_tasks_mod, "_TASK_REGISTRY", {})
    known_tasks = set(_registry) if isinstance(_registry, dict) else set()
    tasks = [t for t in tasks_raw if t and isinstance(t, str) and t in known_tasks]
    if len(tasks) < len(tasks_raw):
        import warnings

        for t in tasks_raw:
            if not t or not isinstance(t, str) or t not in known_tasks:
                warnings.warn(
                    f"run_official_pack: skipping unknown task {t!r}; known: {sorted(known_tasks)}",
                    UserWarning,
                    stacklevel=1,
                )
    baselines_map = pack.get("baselines") or {}
    scale_configs = pack.get("scale_configs") or {}
    required_reports = pack.get("required_reports") or [
        "security",
        "safety_case",
        "transparency_log",
    ]

    if episodes_per_task is None:
        episodes_per_task = 1 if smoke else 50

    ts = (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=seed_base)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1) Baselines: generate-official-baselines into <out>/baselines/
    baselines_dir = out_dir / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)
    task_to_baseline = {}
    for task in tasks:
        bid = baselines_map.get(task) or "scripted_ops_v1"
        task_to_baseline[task] = bid
    from labtrust_gym.benchmarks.runner import run_benchmark

    results_dir = baselines_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    scale_s = scale_configs.get("S", {})
    scale_config_override = None
    if tasks and scale_s and any(t in ("coord_scale", "coord_risk") for t in tasks):
        scale_config_override = _scale_config_to_coordination_scale_config("S", scale_s)

    for i, task in enumerate(tasks):
        if progress_callback is not None:
            try:
                progress_callback(i + 1, len(tasks), f"baseline:{task}")
            except Exception:  # noqa: BLE001
                pass
        bid = task_to_baseline.get(task) or "scripted_ops_v1"
        suffix = bid.replace("_v1", "").replace("_v0", "")
        out_path = results_dir / f"{task}_{suffix}.json"
        coord_method: str | None = None
        if task in ("coord_scale", "coord_risk"):
            coord_method = bid.replace("_v0", "").replace("_v1", "")
            if coord_method.startswith("kernel_"):
                pass
            elif coord_method in (
                "centralized_planner",
                "hierarchical_hub_rr",
                "llm_constrained",
            ):
                pass
            else:
                coord_method = "centralized_planner"
        run_benchmark(
            task_name=task,
            num_episodes=episodes_per_task,
            base_seed=seed_base,
            out_path=out_path,
            repo_root=repo_root,
            scale_config_override=scale_config_override,
            coord_method=coord_method,
            pipeline_mode=pipeline_mode,
            allow_network=allow_network,
            llm_backend=llm_backend,
            metrics_aggregator_id=metrics_aggregator_id,
        )

    # 1b) LLM live: transparency log and live evaluation metadata
    if pipeline_mode == "llm_live":
        try:
            from labtrust_gym.security.transparency import (
                write_llm_live_transparency_log,
            )

            write_llm_live_transparency_log(out_dir)
        except Exception as e:
            (out_dir / "TRANSPARENCY_LOG").mkdir(parents=True, exist_ok=True)
            (out_dir / "TRANSPARENCY_LOG" / "llm_live_error.txt").write_text(str(e), encoding="utf-8")
        # Live evaluation metadata (required by v0.2 protocol): model_id, temperature, tool_registry_fingerprint, allow_network.
        # pipeline_mode and python_version for audit parity with deterministic metadata.
        # First-class wall-clock and LLM latency: aggregate from all task results when present.
        live_meta: dict[str, Any] = {
            "model_id": None,
            "temperature": None,
            "tool_registry_fingerprint": None,
            "allow_network": allow_network,
            "pipeline_mode": "llm_live",
            "python_version": sys.version.split()[0] if sys.version else None,
        }
        latencies_ms: list[float] = []
        wall_s_list: list[float] = []
        step_mean_ms_list: list[float] = []
        for p in sorted(results_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug("Failed to load results JSON %s for live meta: %s", p.name, e)
                continue
            meta = data.get("metadata") or {}
            if live_meta["model_id"] is None:
                live_meta["model_id"] = meta.get("llm_model_id") or data.get("llm_model_id")
            if live_meta["tool_registry_fingerprint"] is None:
                live_meta["tool_registry_fingerprint"] = data.get("tool_registry_fingerprint") or meta.get(
                    "tool_registry_fingerprint"
                )
            if live_meta["temperature"] is None and meta.get("temperature") is not None:
                live_meta["temperature"] = meta.get("temperature")
            for key in ("mean_llm_latency_ms", "p50_llm_latency_ms", "p95_llm_latency_ms"):
                v = meta.get(key)
                if v is not None and isinstance(v, (int, float)):
                    latencies_ms.append(float(v))
            rd = meta.get("run_duration_wall_s")
            if rd is not None and isinstance(rd, (int, float)):
                wall_s_list.append(float(rd))
            step_timing = meta.get("step_timing") or {}
            sm = step_timing.get("step_ms_mean")
            if sm is not None and isinstance(sm, (int, float)):
                step_mean_ms_list.append(float(sm))
        if live_meta["temperature"] is None:
            live_meta["temperature"] = os.environ.get("OPENAI_TEMPERATURE") or os.environ.get("LLM_TEMPERATURE")
        if latencies_ms:
            s = sorted(latencies_ms)
            n = len(s)
            live_meta["llm_latency_ms_p50"] = round(s[int(n * 0.5)] if n else 0, 2)
            live_meta["llm_latency_ms_p95"] = round(s[int(n * 0.95)] if n else 0, 2)
            live_meta["llm_latency_ms_max"] = round(max(latencies_ms), 2)
        if wall_s_list:
            live_meta["wall_clock_s_episode_total"] = round(sum(wall_s_list), 3)
        if step_mean_ms_list:
            live_meta["wall_clock_s_per_step_mean"] = round(sum(step_mean_ms_list) / len(step_mean_ms_list) / 1000.0, 4)
        (out_dir / LIVE_EVALUATION_METADATA_FILENAME).write_text(
            json.dumps(live_meta, indent=2, sort_keys=True), encoding="utf-8"
        )

    # 2) Security suite -> <out>/SECURITY/
    try:
        from labtrust_gym.benchmarks.securitization import emit_securitization_packet
        from labtrust_gym.benchmarks.security_runner import run_suite_and_emit

        run_suite_and_emit(
            policy_root=repo_root,
            out_dir=out_dir,
            repo_root=repo_root,
            smoke_only=not full_security,
            seed=seed_base,
            timeout_s=security_suite_timeout_s,
            metadata={"seed_base": seed_base, "smoke_only": not full_security},
            skip_system_level=skip_system_level,
            progress_callback=progress_callback,
        )
        emit_securitization_packet(repo_root, out_dir)
    except Exception as e:
        (out_dir / "SECURITY").mkdir(parents=True, exist_ok=True)
        (out_dir / "SECURITY" / "run_error.txt").write_text(str(e), encoding="utf-8")

    # 3) Safety case -> <out>/SAFETY_CASE/
    try:
        from labtrust_gym.security.safety_case import emit_safety_case

        emit_safety_case(policy_root=repo_root, out_dir=out_dir)
    except Exception as e:
        (out_dir / "SAFETY_CASE").mkdir(parents=True, exist_ok=True)
        (out_dir / "SAFETY_CASE" / "run_error.txt").write_text(str(e), encoding="utf-8")

    # 4) Transparency log (optional: if receipts exist)
    try:
        from labtrust_gym.security.transparency import write_transparency_log

        if (out_dir / "receipts").exists() or (out_dir / "_repr").exists():
            write_transparency_log(out_dir, out_dir)
        else:
            (out_dir / "TRANSPARENCY_LOG").mkdir(parents=True, exist_ok=True)
            (out_dir / "TRANSPARENCY_LOG" / "README.txt").write_text(
                "No receipts/_repr in pack output; run export-receipts then transparency-log.",
                encoding="utf-8",
            )
    except Exception as e:
        (out_dir / "TRANSPARENCY_LOG").mkdir(parents=True, exist_ok=True)
        (out_dir / "TRANSPARENCY_LOG" / "run_error.txt").write_text(str(e), encoding="utf-8")

    # 4f) Optional: coordination security pack + lab report into coordination_pack/
    coord_pack_config = pack.get("coordination_pack") or {}
    run_coord_pack = (
        include_coordination_pack if include_coordination_pack is not None else bool(coord_pack_config.get("enabled"))
    )
    if run_coord_pack:
        coord_pack_dir = out_dir / "coordination_pack"
        coord_pack_dir.mkdir(parents=True, exist_ok=True)
        matrix_preset = (
            matrix_preset_override
            if matrix_preset_override
            else (coord_pack_config.get("matrix_preset") or "hospital_lab")
        )
        try:
            from labtrust_gym.studies.coordination_security_pack import (
                run_coordination_security_pack,
            )
            from labtrust_gym.studies.lab_report_builder import (
                build_lab_coordination_report,
            )

            run_coordination_security_pack(
                out_dir=coord_pack_dir,
                repo_root=repo_root,
                seed_base=seed_base,
                matrix_preset=matrix_preset,
            )
            build_lab_coordination_report(
                pack_dir=coord_pack_dir,
                out_dir=coord_pack_dir,
                policy_root=repo_root,
                matrix_preset_name=matrix_preset,
            )
        except Exception as e:
            logger.exception("Coordination pack step failed: %s", e)
            (coord_pack_dir / "run_error.txt").write_text(str(e), encoding="utf-8")

    # 5) Pack manifest and summary table
    try:
        git_sha = None
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(repo_root),
        )
        if out.returncode == 0 and out.stdout:
            git_sha = out.stdout.strip()[:12]
    except Exception as e:
        logger.debug("Git rev-parse failed for pack manifest: %s", e)

    manifest = {
        "version": pack_version,
        "pack_policy": pack_policy_path,
        "seed_base": seed_base,
        "timestamp": ts,
        "git_sha": git_sha,
        "smoke": smoke,
        "pipeline_mode": pipeline_mode,
        "allow_network": allow_network,
        "tasks": tasks,
        "baselines": task_to_baseline,
        "scale_configs": list(scale_configs.keys()),
        "coordination_methods": pack.get("coordination_methods") or [],
        "required_reports": required_reports,
        "results_semantics": "v0.2",
    }
    (out_dir / "pack_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        f"# Official Benchmark Pack v{pack_version} – Pack summary",
        "",
        "| Item | Value |",
        "|------|-------|",
        f"| Pack policy | {pack_policy_path} |",
        f"| Seed base | {seed_base} |",
        f"| Timestamp | {ts} |",
        f"| Git SHA | {git_sha or 'n/a'} |",
        f"| Smoke | {smoke} |",
        f"| Tasks | {', '.join(tasks)} |",
        f"| Scale configs | {', '.join(scale_configs.keys())} |",
        f"| Coordination methods | {', '.join(pack.get('coordination_methods') or [])} |",
        f"| Required reports | {', '.join(required_reports)} |",
        f"| Pipeline mode | {pipeline_mode} |",
        "",
        "## Output tree",
        "",
        "```",
        "baselines/results/   (results per task)",
        "SECURITY/            (attack_results.json, coverage, deps)",
        "SAFETY_CASE/         (safety_case.json, safety_case.md)",
        "TRANSPARENCY_LOG/    (log.json, root.txt, proofs/ or README; llm_live.json if llm_live)",
        "pack_manifest.json",
    ]
    if run_coord_pack:
        lines.append(
            "coordination_pack/     (pack_summary.csv, pack_gate.md, SECURITY/, LAB_COORDINATION_REPORT.md, COORDINATION_DECISION.*)"
        )
    if pipeline_mode == "llm_live":
        lines.append(
            f"{LIVE_EVALUATION_METADATA_FILENAME}   (live evaluation metadata: model_id, wall_clock_s_*, llm_latency_ms_* when present)"
        )
    lines.append("PACK_SUMMARY.md")
    lines.append("```")
    lines.append("")
    (out_dir / "PACK_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    return out_dir


def run_cross_provider_pack(
    out_dir: Path,
    repo_root: Path,
    providers: list[str],
    seed_base: int = 100,
    smoke: bool = True,
    full_security: bool = False,
    skip_system_level: bool = False,
) -> Path:
    """
    Run the official pack once per provider (pipeline_mode=llm_live, allow_network=True).
    Writes <out>/<provider>/ for each and <out>/summary_cross_provider.json plus .md.
    """
    out_dir = Path(out_dir).resolve()
    repo_root = Path(repo_root).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict[str, Any]] = []
    for provider in providers:
        provider_dir = out_dir / provider.replace("/", "_")
        run_official_pack(
            out_dir=provider_dir,
            repo_root=repo_root,
            seed_base=seed_base,
            smoke=smoke,
            full_security=full_security,
            pipeline_mode="llm_live",
            allow_network=True,
            llm_backend=provider,
            skip_system_level=skip_system_level,
        )
        row: dict[str, Any] = {"provider": provider, "out_dir": str(provider_dir)}
        live_meta_path = provider_dir / LIVE_EVALUATION_METADATA_FILENAME
        if live_meta_path.exists():
            try:
                row["live_metadata"] = json.loads(live_meta_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug("Failed to load live_metadata from %s: %s", live_meta_path.name, e)
                row["live_metadata"] = None
        llm_live_path = provider_dir / "TRANSPARENCY_LOG" / "llm_live.json"
        if llm_live_path.exists():
            try:
                data = json.loads(llm_live_path.read_text(encoding="utf-8"))
                row["llm_live_version"] = data.get("version")
                row["latency_and_cost"] = data.get("latency_and_cost_statistics")
            except Exception as e:
                logger.debug("Failed to load llm_live.json from %s: %s", provider_dir.name, e)
                row["llm_live_version"] = None
                row["latency_and_cost"] = None
        summary_rows.append(row)
    summary = {
        "seed_base": seed_base,
        "smoke": smoke,
        "providers": providers,
        "runs": summary_rows,
    }
    (out_dir / "summary_cross_provider.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    md_lines = [
        "# Cross-provider pack summary",
        "",
        f"Seed base: {seed_base}, Smoke: {smoke}",
        "",
        "| Provider | Out dir | model_id | mean_latency_ms (agg) |",
        "|----------|---------|----------|------------------------|",
    ]
    for row in summary_rows:
        meta = row.get("live_metadata") or {}
        cost = row.get("latency_and_cost") or {}
        mean_agg = cost.get("mean_latency_ms") or {}
        mean_val = mean_agg.get("mean") if isinstance(mean_agg, dict) else None
        md_lines.append(f"| {row['provider']} | {row['out_dir']} | {meta.get('model_id', 'n/a')} | {mean_val} |")
    (out_dir / "summary_cross_provider.md").write_text("\n".join(md_lines), encoding="utf-8")
    return out_dir
