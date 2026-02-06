"""
Official Benchmark Pack v0.1 runner.

Loads policy/official/benchmark_pack.v0.1.yaml, runs baselines, security suite,
safety case, transparency log; writes a single folder ready to upload.
Results semantics v0.2 canonical. Backward-compatible with existing CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from labtrust_gym.policy.loader import load_yaml

PACK_POLICY_PATH = "policy/official/benchmark_pack.v0.1.yaml"
DEFAULT_ROLE_MIX = {
    "ROLE_RUNNER": 0.4,
    "ROLE_ANALYTICS": 0.3,
    "ROLE_RECEPTION": 0.2,
    "ROLE_QC": 0.05,
    "ROLE_SUPERVISOR": 0.05,
}


def load_benchmark_pack(repo_root: Path) -> dict[str, Any]:
    """Load benchmark_pack.v0.1.yaml. Returns dict with tasks, scale_configs, baselines, etc."""
    path = repo_root / PACK_POLICY_PATH.replace("/", os.sep)
    if not path.exists():
        return {
            "version": "0.1",
            "tasks": {"core": [], "coordination": [], "experimental": []},
            "scale_configs": {},
            "baselines": {},
            "coordination_methods": [],
            "security_suite": {"smoke": {"enabled": True}, "full": {"enabled": False}},
            "required_reports": ["security", "safety_case", "transparency_log"],
        }
    data = load_yaml(path)
    return data if isinstance(data, dict) else {}


def _all_pack_tasks(pack: dict[str, Any]) -> list[str]:
    """Return ordered list of task names (core + coordination + experimental)."""
    out: list[str] = []
    for key in ("core", "coordination", "experimental"):
        out.extend(pack.get("tasks", {}).get(key) or [])
    return out


def _scale_config_to_coordination_scale_config(
    scale_id: str, scale_row: dict[str, Any]
) -> Any:
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
) -> Path:
    """
    Run the official benchmark pack: baselines, SECURITY/, SAFETY_CASE/, TRANSPARENCY_LOG/.
    Returns out_dir. When smoke=True, uses fewer episodes and security smoke-only.
    """
    out_dir = Path(out_dir).resolve()
    repo_root = Path(repo_root).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    pack = load_benchmark_pack(repo_root)
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

    ts = (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(seconds=seed_base)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

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
    if tasks and scale_s and any(t in ("TaskG", "TaskH") for t in tasks):
        scale_config_override = _scale_config_to_coordination_scale_config("S", scale_s)

    for task in tasks:
        bid = task_to_baseline.get(task) or "scripted_ops_v1"
        suffix = bid.replace("_v1", "").replace("_v0", "")
        out_path = results_dir / f"{task}_{suffix}.json"
        coord_method: str | None = None
        if task in ("TaskG", "TaskH"):
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
            metadata={"seed_base": seed_base, "smoke_only": not full_security},
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
        (out_dir / "TRANSPARENCY_LOG" / "run_error.txt").write_text(
            str(e), encoding="utf-8"
        )

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
    except Exception:
        pass

    manifest = {
        "version": "0.1",
        "pack_policy": PACK_POLICY_PATH,
        "seed_base": seed_base,
        "timestamp": ts,
        "git_sha": git_sha,
        "smoke": smoke,
        "tasks": tasks,
        "baselines": task_to_baseline,
        "scale_configs": list(scale_configs.keys()),
        "coordination_methods": pack.get("coordination_methods") or [],
        "required_reports": required_reports,
        "results_semantics": "v0.2",
    }
    (out_dir / "pack_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    lines = [
        "# Official Benchmark Pack v0.1 – Pack summary",
        "",
        "| Item | Value |",
        "|------|-------|",
        f"| Pack policy | {PACK_POLICY_PATH} |",
        f"| Seed base | {seed_base} |",
        f"| Timestamp | {ts} |",
        f"| Git SHA | {git_sha or 'n/a'} |",
        f"| Smoke | {smoke} |",
        f"| Tasks | {', '.join(tasks)} |",
        f"| Scale configs | {', '.join(scale_configs.keys())} |",
        f"| Coordination methods | {', '.join(pack.get('coordination_methods') or [])} |",
        f"| Required reports | {', '.join(required_reports)} |",
        "",
        "## Output tree",
        "",
        "```",
        "baselines/results/   (results per task)",
        "SECURITY/            (attack_results.json, coverage, deps)",
        "SAFETY_CASE/         (safety_case.json, safety_case.md)",
        "TRANSPARENCY_LOG/    (log.json, root.txt, proofs/ or README)",
        "pack_manifest.json",
        "PACK_SUMMARY.md",
        "```",
        "",
    ]
    (out_dir / "PACK_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    return out_dir
