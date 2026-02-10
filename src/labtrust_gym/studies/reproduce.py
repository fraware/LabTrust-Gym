"""
Single CLI path to reproduce a minimal set of results and figures.

Runs a small StudySpec sweep (trust on/off, dual approval on/off) for throughput_sla
and qc_cascade, then generates plots and data tables under runs/<id>/throughput_sla/figures
and qc_cascade/figures.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from labtrust_gym.studies.plots import make_plots
from labtrust_gym.studies.study_runner import run_study


def _minimal_spec(
    task: str,
    episodes: int,
    seed_base: int = 42,
) -> dict[str, Any]:
    """Build minimal reproduce spec: trust_skeleton [on, off], dual_approval [on, off]."""
    return {
        "task": task,
        "episodes": episodes,
        "seed_base": seed_base,
        "timing_mode": "explicit",
        "ablations": {
            "trust_skeleton": ["on", "off"],
            "dual_approval": ["on", "off"],
        },
        "agent_config": "scripted_runner",
    }


def _write_spec_yaml(spec: dict[str, Any], path: Path) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(spec, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def run_reproduce(
    profile: str,
    out_dir: Path | None = None,
    repo_root: Path | None = None,
    seed_base: int | None = None,
) -> Path:
    """
    Run minimal reproduce: throughput_sla and qc_cascade study sweep + plots.

    profile: "minimal" (few episodes), "full" (more episodes), or "full_with_coordination"
        (full + coordination security pack + build-lab-coordination-report into coordination_pack/).
    When LABTRUST_REPRO_SMOKE=1, episodes are set to 1 per condition regardless of profile.
    seed_base: optional fixed seed for determinism (default 100).
    Writes: out_dir/throughput_sla/, out_dir/qc_cascade/ (each with manifest, results, logs, figures).
    When profile is full_with_coordination, also writes out_dir/coordination_pack/ (pack_summary.csv, lab report).
    Returns out_dir.
    """
    repo_root = Path(repo_root) if repo_root else Path.cwd()
    smoke = os.environ.get("LABTRUST_REPRO_SMOKE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    include_coordination = profile == "full_with_coordination"
    base_profile = "full" if include_coordination else profile

    if base_profile == "minimal":
        episodes = 1 if smoke else 2
    elif base_profile == "full":
        episodes = 1 if smoke else 4
    else:
        raise ValueError(
            f"profile must be 'minimal', 'full', or 'full_with_coordination', got {profile!r}"
        )

    if out_dir is None:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_dir = repo_root / "runs" / f"repro_{profile}_{stamp}"
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks: list[str] = ["throughput_sla", "qc_cascade"]
    seed_base = seed_base if seed_base is not None else 100

    for task in tasks:
        spec = _minimal_spec(task=task, episodes=episodes, seed_base=seed_base)
        spec_path = out_dir / f"spec_{task}.yaml"
        _write_spec_yaml(spec, spec_path)
        task_out = out_dir / task.lower()
        run_study(spec_path, task_out, repo_root=repo_root)
        make_plots(task_out)

    if include_coordination:
        coord_dir = out_dir / "coordination_pack"
        coord_dir.mkdir(parents=True, exist_ok=True)
        try:
            from labtrust_gym.studies.coordination_security_pack import (
                run_coordination_security_pack,
            )
            from labtrust_gym.studies.lab_report_builder import (
                build_lab_coordination_report,
            )

            run_coordination_security_pack(
                out_dir=coord_dir,
                repo_root=repo_root,
                seed_base=seed_base,
                matrix_preset="hospital_lab",
            )
            build_lab_coordination_report(
                pack_dir=coord_dir,
                out_dir=coord_dir,
                policy_root=repo_root,
                matrix_preset_name="hospital_lab",
            )
        except Exception as e:
            (coord_dir / "run_error.txt").write_text(str(e), encoding="utf-8")

    return out_dir


def main(
    profile: str,
    out_dir: Path | None = None,
    repo_root: Path | None = None,
    seed_base: int | None = None,
) -> int:
    """CLI entry: run reproduce and write runs/<id>/throughput_sla, qc_cascade with figures."""
    try:
        result = run_reproduce(
            profile=profile, out_dir=out_dir, repo_root=repo_root, seed_base=seed_base
        )
        print(f"Reproduce written to {result}", file=sys.stderr)
        print(
            f"  throughput_sla: {result / 'throughput_sla'}/figures  ({result / 'throughput_sla' / 'RUN_SUMMARY.md'})",
            file=sys.stderr,
        )
        print(
            f"  qc_cascade: {result / 'qc_cascade'}/figures  ({result / 'qc_cascade' / 'RUN_SUMMARY.md'})",
            file=sys.stderr,
        )
        print(
            "  For each task: figures/RUN_REPORT.md explains metrics and figure interpretation.",
            file=sys.stderr,
        )
        return 0
    except Exception as e:
        print(f"reproduce failed: {e}", file=sys.stderr)
        return 1
