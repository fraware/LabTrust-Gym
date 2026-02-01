"""
Single CLI path to reproduce a minimal set of results and figures.

Runs a small StudySpec sweep (trust on/off, dual approval on/off) for TaskA
and TaskC, then generates plots and data tables under runs/<id>/taskA/figures
and taskC/figures.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from labtrust_gym.studies.plots import make_plots
from labtrust_gym.studies.study_runner import run_study


def _minimal_spec(
    task: str,
    episodes: int,
    seed_base: int = 42,
) -> Dict[str, Any]:
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


def _write_spec_yaml(spec: Dict[str, Any], path: Path) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(spec, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def run_reproduce(
    profile: str,
    out_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    seed_base: Optional[int] = None,
) -> Path:
    """
    Run minimal reproduce: TaskA and TaskC study sweep + plots.

    profile: "minimal" (few episodes) or "full" (more episodes).
    When LABTRUST_REPRO_SMOKE=1, episodes are set to 1 per condition regardless of profile.
    seed_base: optional fixed seed for determinism (default 100).
    Writes: out_dir/taskA/, out_dir/taskC/ (each with manifest, results, logs, figures).
    Returns out_dir.
    """
    repo_root = repo_root or Path.cwd()
    smoke = os.environ.get("LABTRUST_REPRO_SMOKE", "").strip().lower() in ("1", "true", "yes")

    if profile == "minimal":
        episodes = 1 if smoke else 2
    elif profile == "full":
        episodes = 1 if smoke else 4
    else:
        raise ValueError(f"profile must be 'minimal' or 'full', got {profile!r}")

    if out_dir is None:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_dir = repo_root / "runs" / f"repro_{profile}_{stamp}"
    out_dir = Path(out_dir)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tasks: List[str] = ["TaskA", "TaskC"]
    seed_base = seed_base if seed_base is not None else 100

    for task in tasks:
        spec = _minimal_spec(task=task, episodes=episodes, seed_base=seed_base)
        spec_path = out_dir / f"spec_{task}.yaml"
        _write_spec_yaml(spec, spec_path)
        task_out = out_dir / task.lower()
        run_study(spec_path, task_out, repo_root=repo_root)
        make_plots(task_out)

    return out_dir


def main(
    profile: str,
    out_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    seed_base: Optional[int] = None,
) -> int:
    """CLI entry: run reproduce and write runs/<id>/taskA, taskC with figures."""
    try:
        result = run_reproduce(
            profile=profile, out_dir=out_dir, repo_root=repo_root, seed_base=seed_base
        )
        print(f"Reproduce written to {result}", file=sys.stderr)
        print(f"  taskA: {result / 'taska'}/figures", file=sys.stderr)
        print(f"  taskC: {result / 'taskc'}/figures", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"reproduce failed: {e}", file=sys.stderr)
        return 1
